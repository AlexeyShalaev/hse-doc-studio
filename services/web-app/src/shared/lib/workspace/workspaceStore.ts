import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Режимы верстака — то, что показывает единственная сменная панель слева.
 * Тип живёт здесь, а не в @widgets/ActivityBar, потому что стор — слой shared
 * и не имеет права импортировать виджет; виджет же импортирует тип отсюда.
 */
export type WorkbenchActivity = "documents" | "review" | "submit" | "files";

type WorkspaceState = {
  // Активный режим панели. Переживает перезагрузку: студент возвращается туда,
  // где работал, а не в дефолтные «Документы».
  activity: WorkbenchActivity;
  sidebarCollapsed: boolean;
  // The global system (no-project) assistant drawer, available everywhere.
  systemChatOpen: boolean;
  // A prompt queued for the agent by another part of the UI (e.g. "fix this
  // build"/"fix this finding"). The chat panel consumes and auto-sends it.
  // Transient — never persisted.
  pendingPrompt: string | null;
};

type WorkspaceActions = {
  setActivity: (activity: WorkbenchActivity) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebar: () => void;
  setSystemChatOpen: (open: boolean) => void;
  toggleSystemChat: () => void;
  // Open the agent panel and queue a prompt to send automatically.
  askAgent: (prompt: string) => void;
  // Take the queued prompt (clearing it). Returns null when nothing is queued.
  consumePendingPrompt: () => string | null;
};

// Persisted so layout choices (agent panel open, active mode, dock) survive a
// page reload, matching how chat width is already remembered.
export const useWorkspaceStore = create<WorkspaceState & WorkspaceActions>()(
  persist(
    (set, get) => ({
      activity: "documents",
      sidebarCollapsed: false,
      systemChatOpen: false,
      pendingPrompt: null,
      setActivity: (activity: WorkbenchActivity) => {
        set({ activity });
      },
      setSidebarCollapsed: (sidebarCollapsed: boolean) => {
        set({ sidebarCollapsed });
      },
      toggleSidebar: () => {
        set({ sidebarCollapsed: !get().sidebarCollapsed });
      },
      setSystemChatOpen: (systemChatOpen: boolean) => {
        set({ systemChatOpen });
      },
      toggleSystemChat: () => {
        set({ systemChatOpen: !get().systemChatOpen });
      },
      askAgent: (prompt: string) => {
        // Route "fix with AI" actions to the one unified agent.
        set({ pendingPrompt: prompt, systemChatOpen: true });
      },
      consumePendingPrompt: () => {
        const prompt = get().pendingPrompt;
        if (prompt !== null) set({ pendingPrompt: null });
        return prompt;
      },
    }),
    {
      // Ключ верстака. Состояние старой раскладки под прежним именем
      // осиротело — мигрировать нечего, система живёт только локально.
      name: "hse-studio-workbench",
      partialize: (state) => ({
        activity: state.activity,
        sidebarCollapsed: state.sidebarCollapsed,
        systemChatOpen: state.systemChatOpen,
      }),
    },
  ),
);
