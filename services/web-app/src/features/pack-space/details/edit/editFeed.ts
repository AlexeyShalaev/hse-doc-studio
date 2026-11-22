import { useSyncExternalStore } from "react";
import type { DeltaItem } from "./model/delta";
import { emptyHistory, type History } from "./model/history";
import type { RuleEdit } from "./model/plan";

// Что человек поправил в условиях и что от этого изменилось в результате. Живёт вне React, по
// версии: переход на другую вкладку и обратно не теряет ленту правок, а центр «Результата»
// (подсветка строк, плашка «что изменилось») читает ту же запись через `useEditFeed`.

export type EditDelta = {
  items: readonly DeltaItem[];
  /** Какая правка вызвала пересчёт. */
  edit: RuleEdit;
  direction: "apply" | "undo" | "redo";
};

export type EditFeed = {
  history: History;
  delta: EditDelta | null;
  /** Ключи `раздел:id` элементов, которые только что изменились: подсветка на несколько секунд. */
  flashed: ReadonlySet<string>;
};

const EMPTY: EditFeed = {
  history: emptyHistory,
  delta: null,
  flashed: new Set(),
};

const feeds = new Map<string, EditFeed>();
const listeners = new Set<() => void>();

export const feedKey = (
  workspaceId: string,
  ref: { pack: string; template: string; version: string },
): string => `${workspaceId}/${ref.pack}/${ref.template}/${ref.version}`;

export const readEditFeed = (key: string): EditFeed => feeds.get(key) ?? EMPTY;

export const writeEditFeed = (
  key: string,
  patch: Partial<EditFeed> | ((prev: EditFeed) => Partial<EditFeed>),
): void => {
  const prev = readEditFeed(key);
  const next = {
    ...prev,
    ...(typeof patch === "function" ? patch(prev) : patch),
  };
  feeds.set(key, next);
  listeners.forEach((listener) => {
    listener();
  });
};

/** Только для тестов: забыть все записи. */
export const resetEditFeeds = (): void => {
  feeds.clear();
  listeners.forEach((listener) => {
    listener();
  });
};

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** Правки и сравнение результата версии `key` (см. `feedKey`). */
export const useEditFeed = (key: string): EditFeed =>
  useSyncExternalStore(
    subscribe,
    () => readEditFeed(key),
    () => EMPTY,
  );
