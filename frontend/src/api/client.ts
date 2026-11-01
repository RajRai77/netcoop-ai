import { getSettings } from '@/state/settings';
import type { ApiErrorBody, Issue } from './types';
import { previewGet } from './preview';
import { CLERK_ENABLED, hasSession, sessionToken } from '@/auth/session';

export class ApiError extends Error {
  status: number;
  code?: string;
  issues: Issue[];
  constructor(status: number, message: string, code?: string, issues: Issue[] = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.issues = issues;
  }
}

export class PreviewWriteError extends Error {
  constructor() {
    super('Preview mode shows a recorded backend run. Connect to a running backend (Settings) to create or diagnose incidents.');
    this.name = 'PreviewWriteError';
  }
}

export function apiUrl(path: string): string {
  const base = getSettings().apiBase.replace(/\/+$/, '');
  return `${base}${path}`;
}

/** Credentials for one request: the Clerk session token (Clerk mode), or the legacy token typed in Settings
 * (local/CI token mode only). Awaited per request so expired session tokens are refreshed transparently. */
export async function authHeaders(): Promise<Record<string, string>> {
  if (CLERK_ENABLED) {
    const t = await sessionToken();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }
  const t = getSettings().apiToken.trim();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export class AuthRequiredError extends ApiError {
  constructor(message: string) {
    super(401, message);
    this.name = 'AuthRequiredError';
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    /* non-JSON error */
  }
  if (body?.error) {
    const issues = body.error.issues ?? [];
    const detail = issues.length ? issues.map((i) => i.message).join(' · ') : body.error.message;
    return new ApiError(res.status, detail, body.error.code, issues);
  }
  const detail = typeof body?.detail === 'string' ? body.detail : body?.detail ? JSON.stringify(body.detail) : res.statusText;
  if (res.status === 401) {
    if (CLERK_ENABLED) {
      return new AuthRequiredError(hasSession() ? 'Session expired or could not be verified. Please sign in again.'
        : 'Sign in with Google to continue.');
    }
    return new ApiError(401, 'Unauthorized: this backend needs an API token (Settings).');
  }
  return new ApiError(res.status, detail || `HTTP ${res.status}`);
}

export async function apiGet<T>(path: string): Promise<T> {
  if (getSettings().preview) return previewGet<T>(path);
  let res: Response;
  try {
    res = await fetch(apiUrl(path), { headers: await authHeaders() });
  } catch {
    throw new ApiError(0, 'Backend unreachable. Start it with scripts/run_local.py or check Settings.');
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export async function apiText(path: string): Promise<string> {
  if (getSettings().preview) throw new PreviewWriteError();
  const res = await fetch(apiUrl(path), { headers: await authHeaders() });
  if (!res.ok) throw await parseError(res);
  return res.text();
}

export async function apiSend<T>(path: string, body: BodyInit | object | undefined, contentType = 'application/json'): Promise<T> {
  if (getSettings().preview) throw new PreviewWriteError();
  const isRaw = typeof body === 'string' || body instanceof Blob || body instanceof ArrayBuffer;
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': contentType, ...(await authHeaders()) },
      body: body === undefined ? undefined : isRaw ? (body as BodyInit) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Backend unreachable. Start it with scripts/run_local.py or check Settings.');
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.code ? `${e.code}: ${e.message}` : e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
