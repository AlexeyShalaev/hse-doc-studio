import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { readUi, writeUi } from "../context/memory";
import { useSpace } from "../context/SpaceContext";
import { PART_IDS, type PartId } from "./model";

// Какие части результата раскрыты, какие списки «Не вошло» открыты и какая часть «текущая».
// Оглавление слева и части в центре это два слота каркаса без общего родителя, поэтому
// состояние живёт в маленьком хранилище. Ключ хранилища: клиент запросов приложения и
// пространство (в галерее у каждой записи свой клиент, поэтому записи не мешают друг другу).
// Раскрытость запоминается в браузере (`readUi`), текущая часть нет.

type State = {
  open: readonly PartId[];
  missing: readonly string[];
  current: PartId;
};

const OPEN_KEY = "result.open";
const MISSING_KEY = "result.missing";
const DEFAULT: State = {
  open: ["documents"],
  missing: [],
  current: "documents",
};

const stores = new WeakMap<QueryClient, Map<string, State>>();
const listeners = new Set<() => void>();

const isPart = (value: string): value is PartId =>
  (PART_IDS as readonly string[]).includes(value);

const list = (raw: unknown): string[] =>
  typeof raw === "string" && raw !== "" ? raw.split(",") : [];

const read = (workspaceId: string): State => {
  const open = readUi(workspaceId, OPEN_KEY);
  return {
    ...DEFAULT,
    open: typeof open === "string" ? list(open).filter(isPart) : DEFAULT.open,
    missing: list(readUi(workspaceId, MISSING_KEY)),
  };
};

const get = (client: QueryClient, workspaceId: string): State => {
  let byWorkspace = stores.get(client);
  if (!byWorkspace) {
    byWorkspace = new Map();
    stores.set(client, byWorkspace);
  }
  let state = byWorkspace.get(workspaceId);
  if (!state) {
    state = read(workspaceId);
    byWorkspace.set(workspaceId, state);
  }
  return state;
};

const put = (client: QueryClient, workspaceId: string, next: State): void => {
  const prev = get(client, workspaceId);
  if (
    prev.open === next.open &&
    prev.missing === next.missing &&
    prev.current === next.current
  ) {
    return;
  }
  stores.get(client)?.set(workspaceId, next);
  if (prev.open !== next.open) {
    writeUi(workspaceId, OPEN_KEY, next.open.join(","));
  }
  if (prev.missing !== next.missing) {
    writeUi(workspaceId, MISSING_KEY, next.missing.join(","));
  }
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

/** Раскрыть ровно эти части и «Не вошло» (галерея и тесты); остальное свернуть. */
export const setOpenParts = (
  client: QueryClient,
  workspaceId: string,
  open: readonly PartId[],
  missing: readonly string[] = [],
): void => {
  put(client, workspaceId, {
    open: PART_IDS.filter((id) => open.includes(id)),
    missing,
    current: get(client, workspaceId).current,
  });
};

/** Идентификатор части в разметке: сюда прокручивает оглавление. */
export const partDomId = (part: PartId): string => `sp-part-${part}`;

const scrollTo = (part: PartId): void => {
  const run = () => {
    const quiet =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(partDomId(part))?.scrollIntoView?.({
      block: "start",
      behavior: quiet ? "auto" : "smooth",
    });
  };
  // Раскрытая часть меняет высоту страницы: прокручиваем после следующей отрисовки.
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(run);
  } else run();
};

const withPart = (open: readonly PartId[], part: PartId): PartId[] =>
  PART_IDS.filter((id) => id === part || open.includes(id));

export type Parts = {
  open: ReadonlySet<PartId>;
  current: PartId;
  toggle: (part: PartId) => void;
  /** Раскрыть часть, сделать текущей и прокрутить к ней (клик в оглавлении). */
  reveal: (part: PartId) => void;
  /** Текущая часть по прокрутке: раскрытость не трогает. */
  setCurrent: (part: PartId) => void;
  /** Открыт ли список «Не вошло» с этим именем, и переключатель. */
  isMissingOpen: (name: string) => boolean;
  toggleMissing: (name: string) => void;
};

export const useParts = (): Parts => {
  const client = useQueryClient();
  const { workspace } = useSpace();
  const id = workspace.id;
  const state = useSyncExternalStore(
    subscribe,
    () => get(client, id),
    () => DEFAULT,
  );
  const toggle = useCallback(
    (part: PartId) => {
      const now = get(client, id);
      put(client, id, {
        ...now,
        open: now.open.includes(part)
          ? now.open.filter((item) => item !== part)
          : withPart(now.open, part),
      });
    },
    [client, id],
  );
  const reveal = useCallback(
    (part: PartId) => {
      const now = get(client, id);
      put(client, id, {
        ...now,
        open: now.open.includes(part) ? now.open : withPart(now.open, part),
        current: part,
      });
      scrollTo(part);
    },
    [client, id],
  );
  const setCurrent = useCallback(
    (part: PartId) => {
      put(client, id, { ...get(client, id), current: part });
    },
    [client, id],
  );
  const toggleMissing = useCallback(
    (name: string) => {
      const now = get(client, id);
      put(client, id, {
        ...now,
        missing: now.missing.includes(name)
          ? now.missing.filter((item) => item !== name)
          : [...now.missing, name],
      });
    },
    [client, id],
  );
  const open = useMemo(() => new Set(state.open), [state.open]);
  return {
    open,
    current: state.current,
    toggle,
    reveal,
    setCurrent,
    isMissingOpen: (name) => state.missing.includes(name),
    toggleMissing,
  };
};
