"""Clerk session authentication and per-user incident isolation (NETCOOP_AUTH_MODE=clerk).

Tokens are real RS256 JWTs signed with a test key pair and verified by the official SDK in networkless mode
(CLERK_JWT_KEY = the public key), so signature, expiry, authorized-party and issuer checks are exercised for real.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from netcoop.api.app import create_app
from netcoop.api.auth import AuthConfigError, Authenticator, issuer_from_publishable_key
from netcoop.config import Settings
from netcoop.storage import make_engine, migrate

SCEN = Path(__file__).resolve().parents[2] / "data" / "scenarios"
HOST = "netcoop-test.clerk.accounts.dev"
PK = "pk_test_" + base64.b64encode(f"{HOST}$".encode()).decode().rstrip("=")
ISS = f"https://{HOST}"
ORIGIN = "https://netcoop.example"


def _keypair():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return k, pem.decode()


KEY, PUB = _keypair()
OTHER_KEY, _ = _keypair()


def token(sub="user_alice", *, key=KEY, iss=ISS, azp=ORIGIN, exp_in=300, sid="sess_1", nbf_in=-5):
    now = int(time.time())
    claims = {"sub": sub, "iss": iss, "azp": azp, "sid": sid, "iat": now - 5, "nbf": now + nbf_in, "exp": now + exp_in}
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "ins_test"})


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def make_client(tmp_path):
    url = f"sqlite:///{(tmp_path / 'auth.db').as_posix()}"
    engine = make_engine(url)
    migrate.upgrade(engine)
    engine.dispose()

    def make(**kw):
        base = dict(database_url=url, auth_mode="clerk", clerk_publishable_key=PK, clerk_jwt_key=PUB,
                    clerk_authorized_parties=(ORIGIN,), allow_in_process_agents=True, scenarios_dir=str(SCEN))
        base.update(kw)
        return TestClient(create_app(Settings(**base)))
    return make


def test_issuer_is_derived_from_publishable_key():
    assert issuer_from_publishable_key(PK) == ISS
    assert issuer_from_publishable_key("not-a-key") is None


def test_health_and_catalog_are_public_but_incidents_are_not(make_client):
    c = make_client()
    assert c.get("/health/live").status_code == 200
    meta = c.get("/api/meta")
    assert meta.status_code == 200 and meta.json()["auth_mode"] == "clerk"
    assert c.get("/api/incidents").status_code == 401
    assert c.post("/api/incidents", json={"scenario_id": "S04-device-down"}).status_code == 401
    assert c.get("/api/raw-records/x").status_code == 401


@pytest.mark.parametrize("bad", [
    pytest.param(lambda: token(exp_in=-120), id="expired"),
    pytest.param(lambda: token(key=OTHER_KEY), id="wrong-signature"),
    pytest.param(lambda: token(iss="https://evil.clerk.accounts.dev"), id="wrong-issuer"),
    pytest.param(lambda: token(azp="https://evil.example"), id="unauthorized-party"),
    pytest.param(lambda: token(sub="org_123"), id="not-a-user"),
    pytest.param(lambda: token(sid=None), id="no-session-id"),
    pytest.param(lambda: token(nbf_in=600), id="not-yet-valid"),
    pytest.param(lambda: token()[:-6] + "AAAAAA", id="tampered"),
    pytest.param(lambda: "not.a.jwt", id="garbage"),
])
def test_invalid_sessions_are_rejected(make_client, bad):
    r = make_client().get("/api/incidents", headers=bearer(bad()))
    assert r.status_code == 401, r.text
    assert r.headers.get("www-authenticate") == "Bearer"


def test_valid_session_is_accepted(make_client):
    r = make_client().get("/api/incidents", headers=bearer(token()))
    assert r.status_code == 200 and r.json() == {"incidents": []}


def test_static_api_token_cannot_bypass_clerk_mode(make_client):
    c = make_client(api_token="legacy-static-token")
    assert c.get("/api/incidents", headers=bearer("legacy-static-token")).status_code == 401


def test_session_cookie_is_not_accepted(make_client):
    c = make_client()
    c.cookies.set("__session", token())  # cookie auth would allow cross-site request forgery
    assert c.get("/api/incidents").status_code == 401


def test_owner_cannot_be_set_by_the_client(make_client):
    r = make_client().post("/api/incidents", headers=bearer(token()), json={"data_mode": "synthetic", "owner_id": "user_x"})
    assert r.status_code == 422


def test_users_cannot_see_each_others_investigations(make_client):
    c = make_client()
    alice, bob = bearer(token("user_alice")), bearer(token("user_bob"))
    r = c.post("/api/incidents", headers=alice, json={"scenario_id": "S04-device-down"})
    assert r.status_code == 201, r.text
    inc = r.json()["incident"]
    iid = inc["incident_id"]
    assert inc["owner_id"] == "user_alice"
    assert c.post(f"/api/incidents/{iid}/diagnose", headers=alice, json={"verification": False}).status_code == 202
    for _ in range(200):
        if c.get(f"/api/incidents/{iid}/report", headers=alice).status_code == 200:
            break
        time.sleep(0.1)
    raw_id = c.get(f"/api/incidents/{iid}/evidence?limit=1", headers=alice).json()["observations"][0]["raw_record_ref"]
    assert c.get(f"/api/raw-records/{raw_id}", headers=alice).status_code == 200

    assert [i["incident_id"] for i in c.get("/api/incidents", headers=alice).json()["incidents"]] == [iid]
    assert c.get("/api/incidents", headers=bob).json()["incidents"] == []
    for method, path in [("GET", ""), ("GET", "/evidence"), ("GET", "/findings"), ("GET", "/timeline"),
                         ("GET", "/topology"), ("GET", "/report"), ("GET", "/report.txt"), ("GET", "/stream"),
                         ("GET", "/attempts/x"), ("POST", "/diagnose"), ("POST", "/telemetry"), ("POST", "/archive")]:
        r = c.request(method, f"/api/incidents/{iid}{path}", headers=bob, json={} if method == "POST" else None)
        assert r.status_code == 404, (method, path, r.status_code)
    assert c.get(f"/api/raw-records/{raw_id}", headers=bob).status_code == 404


def test_pre_auth_records_are_not_exposed(make_client):
    legacy = make_client(auth_mode="none")
    iid = legacy.post("/api/incidents", json={"data_mode": "synthetic"}).json()["incident"]["incident_id"]
    c = make_client()
    assert c.get("/api/incidents", headers=bearer(token())).json()["incidents"] == []
    assert c.get(f"/api/incidents/{iid}", headers=bearer(token())).status_code == 404


@pytest.mark.parametrize("kw,missing", [
    (dict(clerk_publishable_key=None), "CLERK_PUBLISHABLE_KEY"),
    (dict(clerk_authorized_parties=()), "CLERK_AUTHORIZED_PARTIES"),
])
def test_incomplete_clerk_configuration_fails_closed(kw, missing):
    base = dict(database_url=None, auth_mode="clerk", clerk_publishable_key=PK, clerk_jwt_key=PUB,
                clerk_authorized_parties=(ORIGIN,), deployment_env="production")
    base.update(kw)
    with pytest.raises(AuthConfigError, match=missing):
        Authenticator(Settings(**base))


def test_production_never_runs_unauthenticated():
    with pytest.raises(AuthConfigError):
        Authenticator(Settings(database_url=None, deployment_env="production"))
    with pytest.raises(AuthConfigError):
        Authenticator(Settings(database_url=None, auth_mode="bogus"))


def test_legacy_token_mode_is_unchanged(make_client):
    c = make_client(auth_mode=None, api_token="ci-token")
    assert c.get("/api/meta").status_code == 401
    assert c.get("/api/incidents", headers=bearer("ci-token")).status_code == 200
    assert c.get("/api/incidents", headers=bearer(token())).status_code == 401


def _jwks(*keys):
    from jwt.algorithms import RSAAlgorithm
    import json as _json
    out = []
    for kid, k in keys:
        d = _json.loads(RSAAlgorithm.to_jwk(k.public_key()))
        d.update(kid=kid, use="sig", alg="RS256")
        out.append(d)
    return {"keys": out}


def test_public_jwks_verification_without_any_secret():
    from netcoop.api.auth import ClerkVerifier, AuthError
    calls = []
    def fetch():
        calls.append(1)
        return _jwks(("ins_test", KEY))
    v = ClerkVerifier(secret_key=None, jwt_key=None, issuer=ISS, authorized_parties=(ORIGIN,), jwks_fetch=fetch)
    assert v.verify("Bearer " + token("user_alice")) == "user_alice"
    assert v.verify("Bearer " + token("user_bob")) == "user_bob"
    assert len(calls) == 1  # cached
    with pytest.raises(AuthError):
        v.verify("Bearer " + jwt.encode({"sub": "user_x"}, OTHER_KEY, algorithm="RS256", headers={"kid": "ins_other"}))
    with pytest.raises(AuthError):  # right kid, wrong key
        v.verify("Bearer " + token(key=OTHER_KEY))
    with pytest.raises(AuthError):
        v.verify("Bearer " + token(iss="https://evil.clerk.accounts.dev"))


def test_public_jwks_unreachable_fails_closed():
    from netcoop.api.auth import ClerkVerifier, AuthError
    def fetch():
        raise OSError("network down")
    v = ClerkVerifier(secret_key=None, jwt_key=None, issuer=ISS, authorized_parties=(ORIGIN,), jwks_fetch=fetch)
    with pytest.raises(AuthError):
        v.verify("Bearer " + token())
