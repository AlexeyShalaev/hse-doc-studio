import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui/Modal";
import { useSigningRoutes } from "../api/signingRouteQueries";
import {
  affectedHeld,
  guardKey,
  heldDocsOf,
  isOwnTarget,
  routeGuardMemory,
  type GuardDoc,
  type GuardMemory,
  type GuardTarget,
  type HeldDoc,
} from "../lib/editGuard";
import { GuardContext, type GuardScope } from "./routeEditGuardContext";

type GuardRequest = {
  entries: HeldDoc[];
  /** Окно про один документ, к которому относится действие: без перечня. */
  own: boolean;
  resolve: (ok: boolean) => void;
};

export type RouteEditGuardProviderProps = {
  projectId: string;
  /** Маршруты видит вошедший на сервере, который может править проект. */
  enabled: boolean;
  /** Документы проекта: название для окна и папка, по которой файл относится к документу. */
  docs: readonly GuardDoc[];
  children: ReactNode;
  /** Для тестов: своя память вместо `sessionStorage` вкладки. */
  memory?: GuardMemory;
};

export const RouteEditGuardProvider = ({
  projectId,
  enabled,
  docs,
  children,
  memory = routeGuardMemory,
}: RouteEditGuardProviderProps) => {
  const list = useSigningRoutes(projectId, null, { enabled });
  const held = useMemo(() => heldDocsOf(list.data?.items ?? []), [list.data]);
  const ready = !enabled || list.isFetched;
  const [queue, setQueue] = useState<GuardRequest[]>([]);
  // Ушли со страницы с открытым вопросом: ждущие места правки получают «Отмена».
  const queueRef = useRef(queue);
  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);
  useEffect(
    () => () => {
      for (const request of queueRef.current) request.resolve(false);
    },
    [],
  );

  const unanswered = useCallback(
    (entries: readonly HeldDoc[]) =>
      entries.filter((entry) => !memory.has(guardKey(projectId, entry))),
    [memory, projectId],
  );

  // Новые маршруты или документы дают новое значение контекста: места правки перечитывают его.
  const pending = useCallback(
    (target: GuardTarget) => unanswered(affectedHeld(target, held, docs)),
    [unanswered, held, docs],
  );

  const heldNames = useCallback(
    (target: GuardTarget) => namesOf(affectedHeld(target, held, docs), docs),
    [held, docs],
  );

  const remember = useCallback(
    (entries: readonly HeldDoc[]) => {
      for (const entry of entries) memory.add(guardKey(projectId, entry));
    },
    [memory, projectId],
  );

  const confirm = useCallback(
    (target: GuardTarget): Promise<boolean> => {
      const entries = pending(target);
      if (entries.length === 0) return Promise.resolve(true);
      const own = isOwnTarget(target, docs);
      return new Promise<boolean>((resolve) => {
        setQueue((current) => [...current, { entries, own, resolve }]);
      });
    },
    [pending, docs],
  );

  const run = useCallback(
    (target: GuardTarget, action: () => void) => {
      if (pending(target).length === 0) {
        action();
        return;
      }
      void confirm(target).then((ok) => {
        if (ok) action();
      });
    },
    [pending, confirm],
  );

  const acknowledge = useCallback(
    (target: GuardTarget) => {
      remember(pending(target));
    },
    [pending, remember],
  );

  const settle = (ok: boolean) => {
    const [head, ...rest] = queue;
    if (!head) return;
    if (!ok) {
      head.resolve(false);
      setQueue(rest);
      return;
    }
    remember(head.entries);
    head.resolve(true);
    // Ответ мог закрыть и следующие вопросы (два места спросили про один документ).
    const left = rest.filter((request) => {
      if (unanswered(request.entries).length > 0) return true;
      request.resolve(true);
      return false;
    });
    setQueue(left);
  };

  const value = useMemo<GuardScope>(
    () => ({
      projectId,
      ready,
      pending,
      heldNames,
      confirm,
      run,
      acknowledge,
    }),
    [projectId, ready, pending, heldNames, confirm, run, acknowledge],
  );

  const head = queue[0] ?? null;
  return (
    <GuardContext.Provider value={value}>
      {children}
      <RouteEditGuardDialog
        request={head}
        names={head ? namesOf(head.entries, docs) : []}
        onSettle={settle}
      />
    </GuardContext.Provider>
  );
};

const namesOf = (
  entries: readonly HeldDoc[],
  docs: readonly GuardDoc[],
): string[] => {
  const ids = [...new Set(entries.map((entry) => entry.docId))];
  return ids.map((id) => docs.find((doc) => doc.id === id)?.name ?? id);
};

type DialogProps = {
  request: GuardRequest | null;
  names: readonly string[];
  onSettle: (ok: boolean) => void;
};

const RouteEditGuardDialog = ({ request, names, onSettle }: DialogProps) => {
  const { t } = useTranslation("routeEditGuard");
  const count = names.length;
  return (
    <Modal
      isOpen={request !== null}
      onClose={() => {
        onSettle(false);
      }}
      title={t("title", { count })}
      description={
        request?.own
          ? t("single")
          : t("list", { count, names: names.join(", ") })
      }
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={() => {
              onSettle(false);
            }}
          >
            {t("cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => {
              onSettle(true);
            }}
          >
            {t("continue")}
          </button>
        </>
      }
    >
      <p
        className="dim"
        style={{ margin: 0, fontSize: "0.75rem", lineHeight: 1.5 }}
      >
        {t("hint")}
      </p>
    </Modal>
  );
};
