import { createContext } from "react";
import type { OutcomeChange } from "@entities/pack-studio";

/**
 * Слова списка изменений. Без провайдера список показывает подписи и значения сервера как есть
 * (прежний экран). Новая «Проверка» подставляет подписи по-русски, как в паке, а сырой вид и
 * значения сервера складывает в технические подробности (docs/design/pack-studio-ux.md, P5).
 */
export type ChangeWords = {
  words: (change: OutcomeChange) => {
    label: string;
    before: string | null;
    after: string | null;
    tech: readonly { label: string; value: string }[];
  };
  techSummary: string;
};

export const ChangeWordsContext = createContext<ChangeWords | null>(null);
