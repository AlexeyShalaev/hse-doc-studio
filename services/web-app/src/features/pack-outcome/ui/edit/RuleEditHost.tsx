import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  PackStaleFileError,
  cacheModelResult,
  packStudioApi,
  packStudioKeys,
  usePackVersionModel,
  type PackOutcome,
  type PackVersionModel,
  type PackYamlOp,
} from "@entities/pack-studio";
import type { RuleChange, RuleFormContext } from "@features/pack-forms/rule";
import { toast } from "@shared/lib";
import { deltaElement, diffOutcomes } from "../../lib/edit/delta";
import {
  emptyHistory,
  markRedone,
  markUndone,
  pushEdit,
  redoTarget,
  undoTarget,
  type History,
} from "../../lib/edit/history";
import { dataOf, placeOf } from "../../lib/edit/place";
import {
  guardHolds,
  planChange,
  planDelete,
  type Planned,
  type RuleEdit,
} from "../../lib/edit/plan";
import { recordOf } from "../../lib/edit/shape";
import { useOutcomeModel } from "../../model";
import {
  RuleEditContext,
  type EditDelta,
  type EditNotice,
  type EditTarget,
  type RuleEditUi,
} from "./context";

/** Сколько живёт кнопка «Отменить» после удаления записи. */
export const UNDO_MS = 10_000;
/** Сколько элементы, изменившиеся после правки, подсвечены. */
export const FLASH_MS = 4_000;

const NO_KEYS: ReadonlySet<string> = new Set();
const NO_LIST: readonly string[] = [];

type Tracking = {
  baseline: PackOutcome;
  edit: RuleEdit;
  direction: EditDelta["direction"];
  /** Пересчёт после записи уже шёл: его конец означает «результат готов». */
  sawFetching: boolean;
};

/** Поле ввода, где Ctrl+Z принадлежит самому полю: экран не отнимает его. */
const ownsUndo = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.closest(
      "input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable=true], .cm-editor",
    ) !== null
  );
};

let counter = 0;

type RuleEditHostProps = { children: ReactNode };

/**
 * Правка по месту (template-studio-outcome.md, 3.5 и 3.8, срез F7). Держит стек правок экрана,
 * запись теми же точечными правками YAML с `If-Match`, откат и повтор (кнопки и Ctrl+Z), мягкое
 * удаление и сравнение результата до и после записи. Права и состояние версии решает сервер
 * (`read_only` модели): экран только отключает кнопки и объясняет почему.
 */
export const RuleEditHost = ({ children }: RuleEditHostProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { workspaceId, ref, released, phone, url, outcome, shown } = model;
  const client = useQueryClient();
  const student = url.state.mode === "student";
  const available = !phone && !student;

  const versionKey = `${workspaceId}/${ref.pack}/${ref.template}/${ref.version}`;
  const [seenVersion, setSeenVersion] = useState(versionKey);
  const [wanted, setWanted] = useState(false);
  const [history, setHistory] = useState<History>(emptyHistory);
  const [notice, setNotice] = useState<EditNotice | null>(null);
  const [tracking, setTracking] = useState<Tracking | null>(null);
  const [delta, setDelta] = useState<EditDelta | null>(null);
  const [flashed, setFlashed] = useState<ReadonlySet<string>>(NO_KEYS);
  const [live, setLive] = useState("");
  // Стек правок это история одной версии: при смене версии он сбрасывается.
  if (seenVersion !== versionKey) {
    setSeenVersion(versionKey);
    setWanted(false);
    setHistory(emptyHistory);
    setNotice(null);
    setTracking(null);
    setDelta(null);
    setFlashed(NO_KEYS);
  }

  const started = wanted || history.entries.length > 0;
  const modelQuery = usePackVersionModel(
    workspaceId,
    available && started ? ref : null,
  );
  const modelData = modelQuery.data;
  const modelKey = packStudioKeys.model(workspaceId, ref);
  const registry = modelData?.read_only === "releases_read_only";
  const blocked: RuleEditUi["blocked"] = released
    ? "released"
    : url.state.state !== "work_tree"
      ? "state"
      : registry
        ? "registry"
        : null;

  // Самая свежая модель из кэша: правка и откат опираются на неё, а не на последнюю отрисовку.
  const liveModel = (): PackVersionModel | undefined =>
    client.getQueryData<PackVersionModel>(modelKey) ?? modelData;

  const write = useMutation({
    scope: { id: `pack-model:${workspaceId}` },
    mutationFn: ({ file, ops }: { file: string; ops: PackYamlOp[] }) => {
      const current = client.getQueryData<PackVersionModel>(modelKey);
      const etag =
        file === "version.yaml"
          ? current?.manifest.etag
          : current?.documents.find((d) => `files/${d.id}/doc.yaml` === file)
              ?.manifest?.etag;
      return packStudioApi.patchVersionModel(
        workspaceId,
        ref,
        { file, ops },
        etag ?? null,
      );
    },
    onSuccess: (next) => {
      cacheModelResult(client, workspaceId, ref, next);
    },
  });
  const { mutateAsync: send } = write;

  /** Одна запись правок: `true`, если записана; отказ разбирается в плашку. */
  const post = useCallback(
    async (
      file: string,
      ops: PackYamlOp[],
      source: "form" | "history",
    ): Promise<boolean> => {
      try {
        await send({ file, ops });
        return true;
      } catch (error) {
        if (error instanceof PackStaleFileError) {
          setNotice({ source, kind: "stale" });
          void client.invalidateQueries({ queryKey: modelKey });
        } else {
          setNotice({ source, kind: "error", error });
        }
        return false;
      }
    },
    [send, client, modelKey],
  );

  const baselineOf = (): PackOutcome | undefined => shown;

  const track = (edit: RuleEdit, direction: EditDelta["direction"]): void => {
    const baseline = baselineOf();
    if (!baseline) return;
    setDelta(null);
    setTracking({ baseline, edit, direction, sawFetching: false });
  };

  const commit = async (
    planned: Planned,
    source: "form" | "history",
  ): Promise<RuleEdit | null> => {
    if (!planned.ok) {
      if (planned.reason === "missing") {
        setNotice({ source, kind: "missing" });
        void client.invalidateQueries({ queryKey: modelKey });
      }
      return null;
    }
    setNotice(null);
    const ok = await post(planned.edit.file, planned.edit.forward, source);
    if (!ok) return null;
    counter += 1;
    const edit: RuleEdit = {
      ...planned.edit,
      id: `edit-${String(counter)}`,
      at: Date.now(),
    };
    setHistory((h) => pushEdit(h, edit));
    track(edit, "apply");
    setLive(t("edit.live.saved"));
    return edit;
  };

  const labelOf = (target: EditTarget) => ({
    subject: target.kind,
    place: placeOf(
      target.file,
      target.pointer,
      dataOf(liveModel(), target.file),
    ),
  });

  const step = async (
    direction: "undo" | "redo",
    force: boolean,
  ): Promise<void> => {
    const edit =
      direction === "undo" ? undoTarget(history) : redoTarget(history);
    if (!edit) return;
    const data = dataOf(liveModel(), edit.file);
    const guard = direction === "undo" ? edit.after : edit.before;
    if (!force && data !== undefined && !guardHolds(data, guard)) {
      setNotice({ source: "history", kind: "drift", direction });
      return;
    }
    setNotice(null);
    const ok = await post(
      edit.file,
      direction === "undo" ? edit.inverse : edit.forward,
      "history",
    );
    if (!ok) return;
    setHistory((h) => (direction === "undo" ? markUndone(h) : markRedone(h)));
    track(edit, direction);
    setLive(t(direction === "undo" ? "edit.live.undone" : "edit.live.redone"));
  };

  const change = async (
    target: EditTarget,
    next: RuleChange,
  ): Promise<boolean> => {
    const data = dataOf(liveModel(), target.file);
    if (data === undefined) return false;
    const planned = planChange(
      target.file,
      target.pointer,
      data,
      next,
      labelOf(target),
    );
    return (await commit(planned, "form")) !== null;
  };

  const undoById = (id: string): void => {
    if (undoTarget(history)?.id === id) {
      void step("undo", false);
    } else {
      setNotice({
        source: "history",
        kind: "error",
        error: new Error("later"),
      });
    }
  };

  const remove = async (
    target: EditTarget,
    scope: "condition" | "record",
  ): Promise<boolean> => {
    const data = dataOf(liveModel(), target.file);
    if (data === undefined) return false;
    const record = recordOf(target.pointer);
    let planned: Planned;
    if (scope === "record") {
      if (!record) return false;
      planned = planDelete(target.file, record, data, {
        subject: record.kind,
        place: placeOf(target.file, target.pointer, data),
      });
    } else {
      planned = planChange(
        target.file,
        target.pointer,
        data,
        { type: "remove" },
        labelOf(target),
      );
    }
    const edit = await commit(planned, "form");
    if (!edit) return false;
    toast.info(
      t(scope === "record" ? "edit.removed.record" : "edit.removed.condition", {
        what: t(`edit.record.${record?.kind ?? "condition"}`),
      }),
      {
        action: {
          label: t("edit.undo"),
          onClick: () => {
            latest.current.undoById(edit.id);
          },
        },
        duration: UNDO_MS,
      },
    );
    return true;
  };

  // Результат после записи: когда пришёл новый расчёт, сравниваем его с прежним. Состояние
  // выводится при отрисовке (как смена версии выше), чтобы не плодить лишние проходы эффектов.
  if (tracking) {
    const data = outcome.data;
    const fresh =
      data !== undefined &&
      !outcome.isPlaceholderData &&
      data.revision !== tracking.baseline.revision;
    const settled =
      tracking.sawFetching &&
      !outcome.isFetching &&
      !outcome.isPlaceholderData &&
      data !== undefined;
    if (data && (fresh || settled)) {
      const items = diffOutcomes(tracking.baseline, data, i18n.language);
      setDelta({ items, edit: tracking.edit, direction: tracking.direction });
      setFlashed(
        new Set(
          items.map((item) => {
            const el = deltaElement(item);
            return `${el.section}:${el.id}`;
          }),
        ),
      );
      setTracking(null);
      setLive(
        items.length === 0
          ? t("edit.live.same")
          : t("edit.live.delta", {
              added: items.filter((i) => i.symbol === "+").length,
              changed: items.filter((i) => i.symbol === "~").length,
              removed: items.filter((i) => i.symbol === "-").length,
            }),
      );
    } else if (outcome.isFetching && !tracking.sawFetching) {
      setTracking({ ...tracking, sawFetching: true });
    }
  }

  useEffect(() => {
    if (flashed.size === 0) return undefined;
    const timer = setTimeout(() => {
      setFlashed(NO_KEYS);
    }, FLASH_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [flashed]);

  const checks = shown?.checks;
  const formContext = useMemo<RuleFormContext>(
    () => ({
      manifest: modelData?.manifest.data,
      checkRules: modelData?.checks ?? NO_LIST,
      checkCategories: [
        ...new Set(
          (checks ?? []).flatMap((rule) =>
            rule.category ? [rule.category] : [],
          ),
        ),
      ],
    }),
    [modelData, checks],
  );

  const canUndo = undoTarget(history) !== null;
  const canRedo = redoTarget(history) !== null;

  const ui: RuleEditUi = {
    available,
    blocked,
    ready: modelData !== undefined,
    loadFailed: modelQuery.isError ? modelQuery.error : null,
    busy: write.isPending,
    begin: () => {
      setWanted(true);
    },
    data: (file) => dataOf(modelData, file),
    formContext,
    change,
    remove,
    history,
    canUndo,
    canRedo,
    undo: () => {
      void step("undo", false);
    },
    redo: () => {
      void step("redo", false);
    },
    force: (direction) => {
      void step(direction, true);
    },
    notice,
    clearNotice: () => {
      setNotice(null);
    },
    delta,
    dismissDelta: () => {
      setDelta(null);
    },
    flashed,
  };

  // Сочетания клавиш видят самую свежую версию без переподписки на каждый рендер.
  const latest = useRef({ ui, undoById });
  useEffect(() => {
    latest.current = { ui, undoById };
  });
  useEffect(() => {
    if (!available) return undefined;
    const onKey = (event: KeyboardEvent): void => {
      if (event.defaultPrevented || event.altKey) return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const key = event.key.toLowerCase();
      const redo =
        (key === "z" && event.shiftKey) || (key === "y" && !event.shiftKey);
      const undo = key === "z" && !event.shiftKey;
      if (!undo && !redo) return;
      if (ownsUndo(event.target)) return;
      const current = latest.current.ui;
      if (current.blocked !== null || current.busy) return;
      if (redo ? !current.canRedo : !current.canUndo) return;
      event.preventDefault();
      if (redo) current.redo();
      else current.undo();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [available]);

  return (
    <RuleEditContext.Provider value={ui}>
      {children}
      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="outcome-edit-live"
      >
        {live}
      </div>
    </RuleEditContext.Provider>
  );
};
