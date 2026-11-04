import { create } from "zustand";
import type { DocActivity } from "../lib/peopleLib";

// Где вкладка сейчас в документе. Окно документа (виджет) пишет сюда режим, плашка людей в шапке читает:
// страница не знает, редактор это, превью или проверки, а сервер должен получить именно это.

type PlaceState = {
  docId: string | null;
  activity: DocActivity;
  report: (docId: string, activity: DocActivity) => void;
  clear: (docId: string) => void;
};

export const usePlaceStore = create<PlaceState>((set, get) => ({
  docId: null,
  activity: "viewing",
  report: (docId, activity) => {
    set({ docId, activity });
  },
  clear: (docId) => {
    if (get().docId === docId) set({ docId: null, activity: "viewing" });
  },
}));
