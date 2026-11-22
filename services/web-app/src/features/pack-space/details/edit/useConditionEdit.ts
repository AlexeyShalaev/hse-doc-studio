import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useMutation,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  PackStaleFileError,
  cacheModelResult,
  packStudioApi,
  packStudioKeys,
  refreshAfterFileWrite,
  usePackVersionModel,
  type OutcomeCheckRule,
  type PackFileVersion,
  type PackOutcome,
  type PackVersionModel,
  type PackYamlOp,
} from "@entities/pack-studio";
import { deltaElement, diffOutcomes, type DeltaItem } from "./model/delta";
import {
  markRedone,
  markUndone,
  pushEdit,
  redoTarget,
  undoTarget,
  type History,
} from "./model/history";
import { dataOf, fileOf, placeOf } from "./model/place";
import {
  guardHolds,
  planChange,
  type Planned,
  type RuleEdit,
} from "./model/plan";
import type {
  RuleChange,
  RuleFormContext,
  RuleShape,
} from "@features/pack-forms/rule";
import { toast } from "@shared/lib";
import { useSpace } from "../../context/SpaceContext";
import {
  feedKey,
  useEditFeed,
  writeEditFeed,
  type EditDelta,
} from "./editFeed";

// Правка условий по месту: те же точечные записи в описание версии, что у «Содержимого», с
// `If-Match`, лентой правок, откатом и повтором, мягким удалением и сравнением результата до и
// после. Правила сервер уже посчитал: здесь ничего не решается, только пишется и сравнивается.

/** Сколько живёт кнопка «Отменить» после «Убрать условие». */
export const UNDO_MS = 10_000;
/** Сколько изменившиеся элементы подсвечены. */
export const FLASH_MS = 4_000;

const NO_LIST: readonly string[] = [];

/** Запись, которую правит мини-форма. */
export type EditTarget = {
  /** Описание от каталога версии: `version.yaml` или `files/<документ>/doc.yaml`. */
  file: string;
  /** Указатель записи правила. */
  pointer: string;
  shape: RuleShape;
  /** Вид решения (`slot_when`, `skip_if_nda`): по нему подписывается запись в ленте. */
  kind: string;
};

export type EditNotice =
  | { kind: "stale" | "missing" }
  | { kind: "error"; error: unknown }
  // Запись изменилась после правки: откат или повтор перезапишут чужие изменения.
  | { kind: "drift"; direction: "undo" | "redo" };

export type ConditionEdit = {
  /** Правка запрещена: версия выпущена или это выпуск реестра. */
  blocked: "released" | "registry" | null;
  /** Описание версии загружено: форму можно показать. */
  ready: boolean;
  loadFailed: unknown;
  /** Запись ушла на сервер. */
  busy: boolean;
  /** Начать загрузку описания версии (по первому «Изменить условия»). */
  begin: () => void;
  /** Данные описания для формы. */
  data: (file: string) => unknown;
  formContext: RuleFormContext;
  change: (target: EditTarget, change: RuleChange) => Promise<boolean>;
  /** Убрать условие с отменой на десять секунд. */
  remove: (target: EditTarget) => Promise<boolean>;
  history: History;
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
  /** Откат или повтор вопреки предупреждению о чужих изменениях. */
  force: (direction: "undo" | "redo") => void;
  notice: EditNotice | null;
  clearNotice: () => void;
  delta: EditDelta | null;
  dismissDelta: () => void;
  /** Сообщение для скринридера. */
  live: string;
};

/** Файл до правки целиком и ETag, который у него должен быть, чтобы откат был точным. */
type Snapshot = { path: string; before: string; etag: string };

type Tracking = {
  baseline: PackOutcome;
  edit: RuleEdit;
  direction: EditDelta["direction"];
  /** Пересчёт после записи уже шёл: его конец означает «результат готов». */
  sawFetching: boolean;
  /** Сравнение готово: осталось записать его в ленту (делает эффект). */
  items?: DeltaItem[] | undefined;
};

/** Поле ввода, где Ctrl+Z принадлежит самому полю: экран не отнимает его. */
const ownsUndo = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement &&
  target.closest(
    "input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable=true], .cm-editor",
  ) !== null;

let counter = 0;
// Прежний текст файла каждой правки: откат возвращает его целиком, пока файл не тронули после
// правки. Если тронули, остаётся обратная правка значения (чужие изменения файла не теряются).
const snapshots = new Map<string, Snapshot>();

export const useConditionEdit = (
  outcome: UseQueryResult<PackOutcome>,
  checks?: readonly OutcomeCheckRule[],
): ConditionEdit => {
  const { t, i18n } = useTranslation("packSpace");
  const { workspace, versionRef: ref, released } = useSpace();
  const workspaceId = workspace.id;
  const client = useQueryClient();
  const key = feedKey(workspaceId, ref);
  const feed = useEditFeed(key);
  const { history } = feed;
  const shown = outcome.data;

  const [seen, setSeen] = useState(key);
  const [wanted, setWanted] = useState(false);
  const [notice, setNotice] = useState<EditNotice | null>(null);
  const [tracking, setTracking] = useState<Tracking | null>(null);
  const [live, setLive] = useState("");
  // Лента правок это история одной версии (хранится по ключу), остальное сбрасывается.
  if (seen !== key) {
    setSeen(key);
    setWanted(false);
    setNotice(null);
    setTracking(null);
  }

  const started = wanted || history.entries.length > 0;
  const modelQuery = usePackVersionModel(workspaceId, started ? ref : null);
  const modelData = modelQuery.data;
  const modelKey = packStudioKeys.model(workspaceId, ref);
  const blocked: ConditionEdit["blocked"] =
    released || modelData?.read_only === "version_released"
      ? "released"
      : modelData?.read_only === "releases_read_only"
        ? "registry"
        : null;

  // Самая свежая модель из кэша: правка и откат опираются на неё, а не на последнюю отрисовку.
  const liveModel = (): PackVersionModel | undefined =>
    client.getQueryData<PackVersionModel>(modelKey) ?? modelData;

  // «Файл изменили» это ожидаемый исход, а не сбой: он возвращается значением, чтобы общий
  // обработчик ошибок не показал ещё и тост поверх плашки.
  const write = useMutation({
    scope: { id: `pack-model:${workspaceId}` },
    mutationFn: async ({
      file,
      ops,
    }: {
      file: string;
      ops: PackYamlOp[];
    }): Promise<PackVersionModel | PackStaleFileError> => {
      try {
        return await packStudioApi.patchVersionModel(
          workspaceId,
          ref,
          { file, ops },
          fileOf(client.getQueryData<PackVersionModel>(modelKey), file)?.etag ??
            null,
        );
      } catch (error) {
        if (error instanceof PackStaleFileError) return error;
        throw error;
      }
    },
    onSuccess: (next) => {
      if (!(next instanceof PackStaleFileError)) {
        cacheModelResult(client, workspaceId, ref, next);
      }
    },
  });
  const { mutateAsync: send } = write;

  // Откат возвращает файл прежним текстом: так он совпадает с прежним байт в байт, чего не даёт
  // обратная правка значения (удалённый ключ встал бы в конец, список записался бы в строку).
  const restore = useMutation({
    scope: { id: `pack-model:${workspaceId}` },
    mutationFn: async ({
      path,
      text,
      etag,
    }: {
      path: string;
      text: string;
      etag: string;
    }): Promise<PackFileVersion | PackStaleFileError> => {
      try {
        return await packStudioApi.writeFile(workspaceId, path, text, etag);
      } catch (error) {
        if (error instanceof PackStaleFileError) return error;
        throw error;
      }
    },
    onSuccess: async (written, vars) => {
      if (!(written instanceof PackStaleFileError)) {
        await refreshAfterFileWrite(client, workspaceId, ref, vars.path);
      }
    },
  });
  const { mutateAsync: sendRestore } = restore;

  const afterWrite = useCallback(() => {
    void client.invalidateQueries({
      queryKey: packStudioKeys.git(workspaceId),
    });
    void client.invalidateQueries({
      queryKey: packStudioKeys.signaturesAll(workspaceId),
    });
  }, [client, workspaceId]);

  const failure = useCallback(
    (error: unknown) => {
      if (error instanceof PackStaleFileError) {
        setNotice({ kind: "stale" });
        void client.invalidateQueries({ queryKey: modelKey });
      } else {
        setNotice({ kind: "error", error });
      }
    },
    [client, modelKey],
  );

  /** Правка значения: новая модель версии при успехе; отказ разбирается в плашку. */
  const post = useCallback(
    async (
      file: string,
      ops: PackYamlOp[],
    ): Promise<PackVersionModel | null> => {
      try {
        const next = await send({ file, ops });
        if (next instanceof PackStaleFileError) {
          failure(next);
          return null;
        }
        afterWrite();
        return next;
      } catch (error) {
        failure(error);
        return null;
      }
    },
    [send, afterWrite, failure],
  );

  const track = (edit: RuleEdit, direction: EditDelta["direction"]): void => {
    if (!shown) return;
    writeEditFeed(key, { delta: null });
    setTracking({ baseline: shown, edit, direction, sawFetching: false });
  };

  const commit = async (planned: Planned): Promise<RuleEdit | null> => {
    if (!planned.ok) {
      if (planned.reason === "missing") {
        setNotice({ kind: "missing" });
        void client.invalidateQueries({ queryKey: modelKey });
      }
      return null;
    }
    setNotice(null);
    const { file } = planned.edit;
    // Текст до правки: годится, только если файл на диске ровно тот, на который опирается модель.
    const known = fileOf(liveModel(), file);
    let before: string | null = null;
    if (known) {
      try {
        const text = await packStudioApi.readFile(workspaceId, known.path);
        if (text.etag === known.etag) before = text.content;
      } catch {
        before = null;
      }
    }
    const next = await post(file, planned.edit.forward);
    if (!next) return null;
    counter += 1;
    const edit: RuleEdit = {
      ...planned.edit,
      id: `edit-${String(counter)}`,
      at: Date.now(),
    };
    const written = fileOf(next, file);
    if (known && before !== null && written) {
      snapshots.set(edit.id, { path: known.path, before, etag: written.etag });
    }
    writeEditFeed(key, (prev) => ({ history: pushEdit(prev.history, edit) }));
    track(edit, "apply");
    setLive(t("details.edit.live.saved"));
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
    const model = liveModel();
    const data = dataOf(model, edit.file);
    const guard = direction === "undo" ? edit.after : edit.before;
    const snapshot = snapshots.get(edit.id);
    const current = fileOf(model, edit.file);
    // Файл после правки не трогали: откат вернёт прежний текст, ничего чужого он не затрёт.
    const exact =
      direction === "undo" &&
      snapshot !== undefined &&
      current?.etag === snapshot.etag;
    if (!exact && !force && data !== undefined && !guardHolds(data, guard)) {
      setNotice({ kind: "drift", direction });
      return;
    }
    setNotice(null);
    if (exact && snapshot) {
      try {
        const written = await sendRestore({
          path: snapshot.path,
          text: snapshot.before,
          etag: snapshot.etag,
        });
        if (written instanceof PackStaleFileError) {
          failure(written);
          return;
        }
        afterWrite();
        // Повтор пойдёт правкой значения: он вернёт тот же текст, пока файл остаётся этим.
        snapshots.set(edit.id, { ...snapshot, etag: written.etag });
      } catch (error) {
        failure(error);
        return;
      }
      writeEditFeed(key, (prev) => ({ history: markUndone(prev.history) }));
      track(edit, "undo");
      setLive(t("details.edit.live.undone"));
      return;
    }
    const next = await post(
      edit.file,
      direction === "undo" ? edit.inverse : edit.forward,
    );
    if (!next) return;
    const saved = snapshots.get(edit.id);
    const written = fileOf(next, edit.file);
    if (
      direction === "redo" &&
      saved &&
      written &&
      saved.etag === current?.etag
    ) {
      // Файл после отката не трогали: повтор дал прежний текст, следующий откат снова точный.
      snapshots.set(edit.id, { ...saved, etag: written.etag });
    } else {
      snapshots.delete(edit.id);
    }
    writeEditFeed(key, (prev) => ({
      history:
        direction === "undo"
          ? markUndone(prev.history)
          : markRedone(prev.history),
    }));
    track(edit, direction);
    setLive(
      t(
        direction === "undo"
          ? "details.edit.live.undone"
          : "details.edit.live.redone",
      ),
    );
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
    return (await commit(planned)) !== null;
  };

  const remove = async (target: EditTarget): Promise<boolean> => {
    const data = dataOf(liveModel(), target.file);
    if (data === undefined) return false;
    const planned = planChange(
      target.file,
      target.pointer,
      data,
      { type: "remove" },
      labelOf(target),
    );
    const edit = await commit(planned);
    if (!edit) return false;
    toast.info(t("details.edit.removed"), {
      action: {
        label: t("details.edit.undo"),
        onClick: () => {
          latest.current.undoById(edit.id);
        },
      },
      duration: UNDO_MS,
    });
    return true;
  };

  const undoById = (id: string): void => {
    if (undoTarget(history)?.id === id) {
      void step("undo", false);
    } else {
      setNotice({ kind: "error", error: new Error("later") });
    }
  };

  // Результат после записи: когда пришёл новый расчёт, сравниваем его с прежним. Состояние
  // выводится при отрисовке (как смена версии выше), а запись в ленту (внешнее хранилище, на него
  // подписаны и другие части экрана) идёт из эффекта: запись во время отрисовки заставляла соседей
  // обновляться посреди чужой отрисовки, и React ругался.
  if (tracking && tracking.items === undefined) {
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
      setTracking({ ...tracking, items });
      setLive(
        items.length === 0
          ? t("details.edit.live.same")
          : t("details.edit.live.delta", { count: items.length }),
      );
    } else if (outcome.isFetching && !tracking.sawFetching) {
      setTracking({ ...tracking, sawFetching: true });
    }
  }
  useEffect(() => {
    if (!tracking?.items) return;
    const { items, edit, direction } = tracking;
    writeEditFeed(key, {
      delta: { items, edit, direction },
      flashed: new Set(
        items.map((item) => {
          const el = deltaElement(item);
          return `${el.section}:${el.id}`;
        }),
      ),
    });
  }, [tracking, key]);

  const flashedSize = feed.flashed.size;
  useEffect(() => {
    if (flashedSize === 0) return undefined;
    const timer = setTimeout(() => {
      writeEditFeed(key, { flashed: new Set() });
    }, FLASH_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [flashedSize, key]);

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

  const begin = useCallback(() => {
    setWanted(true);
  }, []);

  const ui: ConditionEdit = {
    blocked,
    ready: modelData !== undefined,
    loadFailed: modelQuery.isError ? modelQuery.error : null,
    busy: write.isPending || restore.isPending,
    begin,
    data: (file) => dataOf(modelData, file),
    formContext,
    change,
    remove,
    history,
    canUndo: undoTarget(history) !== null,
    canRedo: redoTarget(history) !== null,
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
    delta: feed.delta,
    dismissDelta: () => {
      writeEditFeed(key, { delta: null });
    },
    live,
  };

  // Сочетания клавиш видят самую свежую версию без переподписки на каждый рендер.
  const latest = useRef({ ui, undoById });
  useEffect(() => {
    latest.current = { ui, undoById };
  });
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.defaultPrevented || event.altKey) return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const pressed = event.key.toLowerCase();
      const redo =
        (pressed === "z" && event.shiftKey) ||
        (pressed === "y" && !event.shiftKey);
      const undo = pressed === "z" && !event.shiftKey;
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
  }, []);

  return ui;
};
