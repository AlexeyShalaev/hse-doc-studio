import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui";
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

/**
 * Мягкое предупреждение правки (docs/design/signing-route.md, 12.7). Места правки спрашивают
 * перед первым изменением документа, который держит идущий маршрут; ответ помнится на сеанс
 * для документа, маршрута и раунда.
 */
export type RouteEditGuard = {
  /** Маршруты проекта загружены (или спрашивать не нужно): решение «спросить» окончательное. */
  ready: boolean;
  /** Документы на подписании без ответа, которые задевает действие. Синхронно, для фильтров. */
  pending: (target: GuardTarget) => HeldDoc[];
  /** Названия всех документов на подписании, которые задевает действие (строка в плане). */
  heldNames: (target: GuardTarget) => string[];
  /** Спросить, если нужно: true, когда можно менять. */
  confirm: (target: GuardTarget) => Promise<boolean>;
  /**
   * Выполнить действие: сразу, если спрашивать не о чем (синхронно, как без предупреждения),
   * иначе после «Продолжить». «Отмена» действие не выполняет.
   */
  run: (target: GuardTarget, action: () => void) => void;
  /** Запомнить ответ без окна: автор видел предупреждение в другом месте (план обновления). */
  acknowledge: (target: GuardTarget) => void;
};

type GuardScope = RouteEditGuard & { projectId: string };

const NO_GUARD: RouteEditGuard = {
  ready: true,
  pending: () => [],
  heldNames: () => [],
  confirm: () => Promise.resolve(true),
  run: (_target, action) => {
    action();
  },
  acknowledge: () => undefined,
};

const GuardContext = createContext<GuardScope | null>(null);

/**
 * Предупреждение для правки проекта. Вне `RouteEditGuardProvider` этого проекта (локальная
 * Студия, гость, тесты отдельных мест) не спрашивает ничего.
 */
export const useRouteEditGuard = (projectId: string): RouteEditGuard => {
  const scope = useContext(GuardContext);
  return scope?.projectId === projectId ? scope : NO_GUARD;
};

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
  const held = useMemo(
    () => heldDocsOf(list.data?.items ?? []),
    [list.data],
  );
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

  // Фильтр редактора читает состояние синхронно и создаётся один раз: свежие данные через ref.
  const stateRef = useRef({ held, docs });
  useEffect(() => {
    stateRef.current = { held, docs };
  }, [held, docs]);

  const unanswered = useCallback(
    (entries: readonly HeldDoc[]) =>
      entries.filter((entry) => !memory.has(guardKey(projectId, entry))),
    [memory, projectId],
  );

  const pending = useCallback(
    (target: GuardTarget) => {
      const { held: current, docs: known } = stateRef.current;
      return unanswered(affectedHeld(target, current, known));
    },
    [unanswered],
  );

  const heldNames = useCallback((target: GuardTarget) => {
    const { held: current, docs: known } = stateRef.current;
    return namesOf(affectedHeld(target, current, known), known);
  }, []);

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
      const own = isOwnTarget(target, stateRef.current.docs);
      return new Promise<boolean>((resolve) => {
        setQueue((current) => [...current, { entries, own, resolve }]);
      });
    },
    [pending],
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
