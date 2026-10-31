import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** apiBase '' = same origin (Vite dev/preview proxy). Otherwise e.g. http://127.0.0.1:8000 (needs
 * the backend started with --cors-origin <this UI's origin>). */
export interface Settings {
  apiBase: string;
  apiToken: string;
  /** Preview = recorded responses of a real backend run, clearly labeled; never mixed with live data. */
  preview: boolean;
  reducedMotion: boolean;
}

interface AppState extends Settings {
  activeIncidentId: string | null;
  selectedScenarioId: string | null;
  set: (p: Partial<Settings & { activeIncidentId: string | null; selectedScenarioId: string | null }>) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      apiBase: '',
      apiToken: '',
      preview: false,
      reducedMotion: false,
      activeIncidentId: null,
      selectedScenarioId: 'S19-ap-down-status-in-archive',
      set: (p) => set(p),
    }),
    { name: 'netcoop-ui-v2' },
  ),
);

export const getSettings = () => useApp.getState();
