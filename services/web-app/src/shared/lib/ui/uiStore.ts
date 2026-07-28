import { create } from "zustand";

// Settings moved from a modal to a real route (/settings/:section), so its
// open / deep-link state now lives in the URL, not here.
type UIState = {
  paletteOpen: boolean;
};

type UIActions = {
  setPaletteOpen: (open: boolean) => void;
  togglePaletteOpen: () => void;
};

export const useUIStore = create<UIState & UIActions>((set, get) => ({
  paletteOpen: false,
  setPaletteOpen: (open: boolean) => {
    set({ paletteOpen: open });
  },
  togglePaletteOpen: () => {
    set({ paletteOpen: !get().paletteOpen });
  },
}));
