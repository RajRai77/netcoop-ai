// Clerk-dependent UI. Only rendered when VITE_CLERK_PUBLISHABLE_KEY is set (CLERK_ENABLED), i.e. inside <ClerkProvider>.
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { HandleSSOCallback, useAuth, useClerk, useSession, useSignIn, useUser, UserButton } from '@clerk/react';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { LogOut, ShieldCheck } from 'lucide-react';
import { useApp } from '@/state/settings';
import { CLERK_ENABLED, setSessionTokenGetter } from './session';
import { Chip, Logo } from '@/components/ui';

/** Installs the session-token getter (synchronously, before any child can query the API) and isolates accounts:
 * when the signed-in user changes or signs out, cached results, the active incident and streams are dropped. */
export function AuthBridge({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth();
  const qc = useQueryClient();
  const uid = isLoaded && isSignedIn ? userId ?? null : null;
  setSessionTokenGetter(uid ? () => getToken() : null, uid ?? 'anon');
  const prev = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!isLoaded) return;
    const stored = useApp.getState().authUser;
    if ((prev.current !== undefined && prev.current !== uid) || stored !== uid) {
      void qc.cancelQueries();
      qc.clear();
      useApp.getState().set({ activeIncidentId: null, authUser: uid });
    }
    prev.current = uid;
  }, [isLoaded, uid, qc]);
  return <>{children}</>;
}

const GOOGLE = (
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
    <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.4-.4-3.5z" />
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
    <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.2-.1-2.4-.4-3.5z" />
  </svg>
);

/** Google sign-in through Clerk: straight to Google's account chooser; Clerk's own sign-in UI as the fallback. */
export function GoogleButton({ label = 'Continue with Google', className = 'btn primary big' }: { label?: string; className?: string }) {
  const { signIn } = useSignIn();
  const clerk = useClerk();
  const { isLoaded } = useAuth();
  const [busy, setBusy] = useState(false);
  const fallback = () => clerk.openSignIn({ forceRedirectUrl: '/command' });
  const go = async () => {
    setBusy(true);
    try {
      const origin = window.location.origin;
      const { error } = await signIn.sso({ strategy: 'oauth_google', redirectUrl: `${origin}/command`, redirectCallbackUrl: `${origin}/sso-callback` });
      if (error) throw error;
    } catch {
      setBusy(false);
      fallback();
    }
  };
  return (
    <button className={className} onClick={go} disabled={busy || !isLoaded} title={isLoaded ? undefined : 'Loading sign-in'}>
      <span style={{ display: 'inline-grid', placeItems: 'center', width: 22, height: 22, borderRadius: 6, background: '#fff' }}>{GOOGLE}</span>
      {!isLoaded ? 'Loading sign-in…' : busy ? 'Opening Google…' : label}
    </button>
  );
}

/** /sso-callback: completes the Google redirect and lands in the Command Center. */
export function SsoCallback() {
  const navigate = useNavigate();
  const clerk = useClerk();
  const to = (dest: string) => (dest.startsWith('http') ? window.location.assign(dest) : navigate(dest, { replace: true }));
  return (
    <div className="auth-gate">
      <div className="auth-card glass strong" role="status">
        <Logo size={56} />
        <h1>Signing you in…</h1>
        <p className="muted">Completing Google sign-in securely through Clerk.</p>
        <HandleSSOCallback
          navigateToApp={({ decorateUrl }) => to(decorateUrl('/command'))}
          navigateToSignIn={() => { navigate('/', { replace: true }); clerk.openSignIn({ forceRedirectUrl: '/command' }); }}
          navigateToSignUp={() => { navigate('/', { replace: true }); clerk.openSignUp({ forceRedirectUrl: '/command' }); }}
        />
      </div>
    </div>
  );
}

function Gate({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (isLoaded) return;
    const t = setTimeout(() => setSlow(true), 15000);
    return () => clearTimeout(t);
  }, [isLoaded]);
  if (!isLoaded) {
    return (
      <div className="auth-gate">
        <div className="auth-card glass strong" role="status">
          <Logo size={48} />
          {slow ? <><h1>Unable to verify your session</h1><p className="muted">The sign-in service could not be reached. Check your connection or content blockers, then reload.</p>
            <button className="btn" onClick={() => window.location.reload()}>Reload</button><Link to="/" className="btn ghost sm">Back to overview</Link></>
            : <p className="muted">Checking your session…</p>}
        </div>
      </div>
    );
  }
  if (!isSignedIn) return <SignInGate />;
  return <>{children}</>;
}

/** Application routes need a verified session in Clerk mode (the API enforces it too). Preview mode is public. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const preview = useApp((s) => s.preview);
  if (!CLERK_ENABLED || preview) return <>{children}</>;
  return <Gate>{children}</Gate>;
}

export function SignInGate() {
  return (
    <div className="auth-gate">
      <div className="auth-card glass strong">
        <Logo size={64} />
        <h1>Sign in to start investigating</h1>
        <p className="muted">
          NetCoop AI runs real multi-agent diagnoses. Sign in with your Google account; your investigations are private
          to your account.
        </p>
        <GoogleButton />
        <Link to="/" className="btn ghost sm">Back to overview</Link>
        <p className="auth-fine">Secured by Clerk. NetCoop never sees your Google password and stores only your Clerk user id with your investigations.</p>
      </div>
    </div>
  );
}

/** Header profile: avatar menu (Clerk) with the user's name. */
export function UserMenu() {
  const { user } = useUser();
  if (!user) return null;
  return (
    <div className="user-menu">
      <span className="user-name">{user.fullName || user.primaryEmailAddress?.emailAddress}</span>
      <UserButton />
    </div>
  );
}

/** Landing-page header/CTA area for Clerk mode. */
export function LandingAuth({ signedIn, signedOut }: { signedIn: ReactNode; signedOut: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  return <>{isLoaded && isSignedIn ? signedIn : signedOut}</>;
}

/** Settings: who is signed in, how, and session state. Never shows the token itself. */
export function AccountPanel() {
  const { user } = useUser();
  const { session } = useSession();
  const clerk = useClerk();
  if (!user) return null;
  const google = user.externalAccounts?.find((a) => a.provider === 'google');
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <img src={user.imageUrl} alt="" width={48} height={48} style={{ borderRadius: '50%' }} />
        <div>
          <div style={{ fontWeight: 700 }}>{user.fullName || 'Signed in'}</div>
          <div className="muted">{user.primaryEmailAddress?.emailAddress}</div>
        </div>
        <Chip tone="green" pip>Signed in</Chip>
      </div>
      <dl className="kv">
        <dt>Provider</dt><dd>{google ? 'Google (via Clerk)' : 'Clerk'}</dd>
        <dt>Session</dt><dd>{session?.status === 'active' ? 'active · short-lived tokens refreshed automatically' : session?.status ?? '—'}</dd>
        <dt>Last active</dt><dd>{session?.lastActiveAt ? session.lastActiveAt.toLocaleString() : '—'}</dd>
        <dt>Privacy</dt><dd>Investigations you create are visible only to this account.</dd>
      </dl>
      <div><button className="btn" onClick={() => clerk.signOut({ redirectUrl: '/' })}><LogOut size={16} />Sign out</button></div>
      <div className="panel-sub"><ShieldCheck size={13} style={{ verticalAlign: -2 }} /> The API verifies every request's Clerk session server-side; no API token is ever entered here.</div>
    </div>
  );
}
