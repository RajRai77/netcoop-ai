import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClerkProvider } from '@clerk/react';
import '@fontsource-variable/inter';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './styles/app.css';
import { App } from './App';
import { ApiError } from './api/client';
import { CLERK_ENABLED, CLERK_PUBLISHABLE_KEY } from './auth/session';
import { AuthBridge } from './auth/clerk';

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
      // never retry authentication/authorization failures (no 401 loops); one retry for transient errors
      retry: (count, err) => !(err instanceof ApiError && [401, 403, 404].includes(err.status)) && count < 1,
    },
  },
});

const app = <App />;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      {CLERK_ENABLED ? (
        <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY!} afterSignOutUrl="/"
                       signInForceRedirectUrl="/command" signUpForceRedirectUrl="/command">
          <AuthBridge>{app}</AuthBridge>
        </ClerkProvider>
      ) : app}
    </QueryClientProvider>
  </StrictMode>,
);
