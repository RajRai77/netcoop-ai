// Session plumbing shared by the API client and the SSE stream.
// In Clerk mode the short-lived session token comes from Clerk's getToken() on every request (Clerk caches and
// refreshes it). It is never stored in Zustand/localStorage and never logged.

export const CLERK_PUBLISHABLE_KEY = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim() || undefined;
export const CLERK_ENABLED = !!CLERK_PUBLISHABLE_KEY;

type Getter = () => Promise<string | null>;
let getter: Getter | null = null;
let scope = 'anon';

/** Installed by <AuthBridge/> inside ClerkProvider. */
export function setSessionTokenGetter(g: Getter | null, userScope: string) {
  getter = g;
  scope = userScope;
}

/** The current Clerk session token, or null when signed out / not yet loaded. */
export async function sessionToken(): Promise<string | null> {
  if (!getter) return null;
  try {
    return await getter();
  } catch {
    return null;
  }
}

export const hasSession = () => getter !== null;

/** Query-cache scope: results of different accounts never share cache keys. */
export const userScope = () => scope;
