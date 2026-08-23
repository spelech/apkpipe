import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  manualModalOpen: boolean;
  setManualModalOpen: (open: boolean) => void;
  autoRefreshQueue: boolean;
  setAutoRefreshQueue: (enabled: boolean) => void;
  queuePollingInterval: number;
  setQueuePollingInterval: (interval: number) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      manualModalOpen: false,
      setManualModalOpen: (open) => set({ manualModalOpen: open }),
      autoRefreshQueue: true,
      setAutoRefreshQueue: (enabled) => set({ autoRefreshQueue: enabled }),
      queuePollingInterval: 5000,
      setQueuePollingInterval: (interval) => set({ queuePollingInterval: interval }),
    }),
    {
      name: 'apkpipe-ui-storage',
      partialize: (state) => ({
        autoRefreshQueue: state.autoRefreshQueue,
        queuePollingInterval: state.queuePollingInterval,
      }),
    }
  )
);
