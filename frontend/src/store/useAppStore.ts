import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ConnectionStatus, AppSettings } from '@/types';

interface AppState {
  settings: AppSettings;
  connection: ConnectionStatus;
  activeIncidentId: string | null;

  updateSettings: (partial: Partial<AppSettings>) => void;
  setConnection: (status: Partial<ConnectionStatus>) => void;
  setActiveIncident: (id: string | null) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      settings: {
        backendUrl: 'http://localhost:8000',
        apiToken: undefined,
        useFixtureData: true,
        reducedMotion: false,
      },
      connection: {
        connected: false,
        checking: false,
      },
      activeIncidentId: null,

      updateSettings: (partial) =>
        set((s) => ({ settings: { ...s.settings, ...partial } })),

      setConnection: (partial) =>
        set((s) => ({ connection: { ...s.connection, ...partial } })),

      setActiveIncident: (id) => set({ activeIncidentId: id }),
    }),
    {
      name: 'netcoop-app-store',
      partialize: (s) => ({ settings: s.settings, activeIncidentId: s.activeIncidentId }),
    },
  ),
);
