"""Authentication for the API: explicit modes, fail-closed configuration, verified Clerk sessions.

Modes (NETCOOP_AUTH_MODE):
  * clerk - every protected request needs a Clerk *session* token (Authorization: Bearer <jwt>) verified with the
            official SDK (clerk-backend-api `authenticate_request`): RS256 signature (instance JWKS via the secret key,
            or networkless with CLERK_JWT_KEY), exp/nbf, authorized party (azp). The SDK does not check the issuer, so it
            is checked here against the instance's frontend-API URL. Incidents are owned by the verified `sub`.
            The static NETCOOP_API_TOKEN is never accepted in this mode.
  * token - legacy single-operator mode (CI, CLI, Compose): one static bearer token (constant-time compare).
  * none  - local development only; refused when NETCOOP_ENV=production.
Default when NETCOOP_AUTH_MODE is unset: token if NETCOOP_API_TOKEN is set, otherwise none (unchanged behaviour).
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import threading
import time
import urllib.request
from dataclasses import dataclass
from types import SimpleNamespace

AUTH_MODES = ("none", "token", "clerk")


class AuthConfigError(ValueError):
    """Refuse to start with an authentication configuration that would be unsafe or cannot verify anything."""


class AuthError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Principal:
    mode: str
    user_id: str | None = None  # verified Clerk user id (clerk mode only)

    @property
    def multi_user(self) -> bool:
        return self.mode == "clerk"


def issuer_from_publishable_key(pk: str) -> str | None:
    """pk_test_/pk_live_ + base64("<frontend-api-host>$") -> https://<frontend-api-host> (Clerk key format)."""
    for prefix in ("pk_test_", "pk_live_"):
        if pk.startswith(prefix):
            raw = pk[len(prefix):]
            try:
                host = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError):
                return None
            return f"https://{host[:-1]}" if host.endswith("$") and len(host) > 1 else None
    return None


class PublicJwks:
    """The instance's PUBLIC signing keys from <issuer>/.well-known/jwks.json (no secret needed). Cached for an hour;
    an unknown key id triggers at most one refetch per minute (key rotation)."""

    def __init__(self, issuer: str, fetch=None):
        self.url = issuer.rstrip("/") + "/.well-known/jwks.json"
        self._fetch = fetch or self._http
        self._keys: dict[str, str] = {}
        self._at = 0.0
        self._lock = threading.Lock()

    def _http(self) -> dict:
        with urllib.request.urlopen(self.url, timeout=10) as r:
            return json.loads(r.read())

    def _refresh(self) -> None:
        from jwt.algorithms import RSAAlgorithm
        from cryptography.hazmat.primitives import serialization

        keys = {}
        for k in self._fetch().get("keys", []):
            if k.get("kty") == "RSA" and k.get("kid"):
                pub = RSAAlgorithm.from_jwk(json.dumps(k))
                keys[k["kid"]] = pub.public_bytes(serialization.Encoding.PEM,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self._keys, self._at = keys, time.monotonic()

    def pem_for(self, kid: str | None) -> str | None:
        with self._lock:
            age = time.monotonic() - self._at
            if not self._keys or age > 3600 or (kid not in self._keys and age > 60):
                try:
                    self._refresh()
                except Exception:  # network failure: keep the cached keys; unknown kid -> rejected (fail closed)
                    pass
            return self._keys.get(kid) if kid else None


class ClerkVerifier:
    def __init__(self, *, secret_key: str | None, jwt_key: str | None, issuer: str, authorized_parties: tuple[str, ...],
                 jwks_fetch=None):
        from clerk_backend_api.security.types import AuthenticateRequestOptions

        self.issuer = issuer.rstrip("/")
        self.authorized_parties = list(authorized_parties)
        self.secret_key = secret_key or None
        self.jwt_key = (jwt_key or "").replace("\\n", "\n") or None
        # Without a secret or a configured PEM key, verify against the instance's published public keys.
        self.jwks = PublicJwks(self.issuer, jwks_fetch) if not (self.secret_key or self.jwt_key) else None
        self._opts = AuthenticateRequestOptions

    def _options(self, token: str):
        jwt_key = self.jwt_key
        if self.jwks is not None:
            import jwt as pyjwt

            try:
                kid = pyjwt.get_unverified_header(token).get("kid")  # only selects which public key to verify with
            except pyjwt.PyJWTError:
                kid = None
            jwt_key = self.jwks.pem_for(kid)
            if jwt_key is None:
                raise AuthError("session not verified (unknown signing key)")
        return self._opts(secret_key=self.secret_key, jwt_key=jwt_key, authorized_parties=self.authorized_parties,
                          accepts_token=["session_token"])  # no machine / API-key / OAuth tokens

    def verify(self, authorization: str | None) -> str:
        from clerk_backend_api.security import authenticate_request

        if not authorization or not authorization.lower().startswith("bearer ") or len(authorization) < 12:
            raise AuthError("session token missing")
        # Only the Authorization header is passed on: the SDK would otherwise also accept a __session cookie,
        # which would make state-changing requests forgeable cross-site (CSRF).
        token = authorization[7:].strip()
        state = authenticate_request(SimpleNamespace(headers={"Authorization": "Bearer " + token}), self._options(token))
        if not state.is_signed_in or not state.payload:
            raise AuthError(f"session not verified ({state.reason.name if state.reason else 'unknown'})")
        claims = state.payload
        if str(claims.get("iss", "")).rstrip("/") != self.issuer:
            raise AuthError("session not verified (issuer)")
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub.startswith("user_") or not claims.get("sid"):
            raise AuthError("session not verified (not a user session)")
        return sub


class Authenticator:
    def __init__(self, settings):
        mode = settings.auth_mode
        if mode not in AUTH_MODES:
            raise AuthConfigError(f"NETCOOP_AUTH_MODE={mode!r}; use one of {AUTH_MODES}")
        production = settings.deployment_env == "production"
        self.mode = mode
        self.token = None
        self.clerk: ClerkVerifier | None = None
        if mode == "none" and production:
            raise AuthConfigError("NETCOOP_ENV=production requires authentication (NETCOOP_AUTH_MODE=clerk or token)")
        if mode == "token":
            if not settings.api_token:
                raise AuthConfigError("NETCOOP_AUTH_MODE=token requires NETCOOP_API_TOKEN")
            self.token = settings.api_token
        if mode == "clerk":
            missing = []
            issuer = settings.clerk_issuer or issuer_from_publishable_key(settings.clerk_publishable_key or "")
            if not issuer:
                missing.append("CLERK_PUBLISHABLE_KEY (or CLERK_ISSUER)")
            if not settings.clerk_authorized_parties:
                missing.append("CLERK_AUTHORIZED_PARTIES (the app's https origins)")
            if missing:
                raise AuthConfigError("NETCOOP_AUTH_MODE=clerk is missing " + ", ".join(missing))
            # Key material: CLERK_SECRET_KEY (SDK fetches JWKS via the Backend API), CLERK_JWT_KEY (PEM), or neither:
            # then the instance's public JWKS endpoint, derived from the issuer, is used.
            self.clerk = ClerkVerifier(secret_key=settings.clerk_secret_key, jwt_key=settings.clerk_jwt_key,
                                       issuer=issuer, authorized_parties=settings.clerk_authorized_parties)

    def authenticate(self, authorization: str | None) -> Principal:
        if self.mode == "none":
            return Principal("none")
        if self.mode == "token":
            supplied = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(supplied.encode(), self.token.encode()):
                raise AuthError("missing or invalid bearer token")
            return Principal("token")
        return Principal("clerk", self.clerk.verify(authorization))
