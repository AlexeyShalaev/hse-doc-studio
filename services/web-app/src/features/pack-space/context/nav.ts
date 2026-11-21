import {
  SPACE_QUERY,
  spacePath,
  type PackVersionRef,
  type SpaceTab,
} from "@entities/pack-studio";
import { isCaseId, writeInputs } from "./situation";

/**
 * Что изменить в адресе. Не упомянутое остаётся как было, `null` убирает параметр. Срезы не
 * собирают адреса руками: всё идёт через `useSpaceNav().go/href` и этот тип.
 */
export type SpaceNavPatch = {
  /** Другая версия (пак, шаблон или версия). Как смена вкладки, сбрасывает параметры вкладки. */
  ref?: PackVersionRef;
  tab?: SpaceTab;
  doc?: string | null;
  part?: string | null;
  file?: string | null;
  /** Выбранный элемент результата: `<раздел>:<id>`. */
  sel?: string | null;
  /** Панель «Изменения». */
  changes?: boolean;
  /** Все условия студента целиком (прежние заменяются). */
  inputs?: Record<string, string>;
  case?: string | null;
  /** Параметры области, у которых нет своего поля (`at`, `from`, `compare`, ...). */
  extra?: Record<string, string | null>;
};

export type SpaceHere = {
  workspaceId: string;
  ref: PackVersionRef;
  tab: SpaceTab;
  search: string;
};

const sameRef = (a: PackVersionRef, b: PackVersionRef): boolean =>
  a.pack === b.pack && a.template === b.template && a.version === b.version;

/** Переход на другую вкладку или версию: в историю идёт новой записью, а не заменой. */
export const isMove = (here: SpaceHere, patch: SpaceNavPatch): boolean =>
  (patch.tab !== undefined && patch.tab !== here.tab) ||
  (patch.ref !== undefined && !sameRef(patch.ref, here.ref));

// Переживают переход: условия студента, готовый случай и открытая панель «Изменения».
const sticky = (name: string): boolean =>
  name.startsWith(SPACE_QUERY.inputPrefix) ||
  name === SPACE_QUERY.case ||
  name === SPACE_QUERY.changes;

/** Адрес после применения `patch` к текущему месту. */
export const buildSpaceUrl = (
  here: SpaceHere,
  patch: SpaceNavPatch = {},
): string => {
  const moved = isMove(here, patch);
  const next = new URLSearchParams();
  new URLSearchParams(here.search).forEach((value, name) => {
    if (!moved || sticky(name)) next.append(name, value);
  });
  const put = (name: string, value: string | null | undefined) => {
    if (value === undefined) return;
    if (value === null || value === "") next.delete(name);
    else next.set(name, value);
  };
  put(SPACE_QUERY.doc, patch.doc);
  put(SPACE_QUERY.part, patch.part);
  put(SPACE_QUERY.file, patch.file);
  put(SPACE_QUERY.sel, patch.sel);
  if (patch.changes !== undefined) {
    put(SPACE_QUERY.changes, patch.changes ? "1" : null);
  }
  if (patch.inputs) writeInputs(next, patch.inputs);
  if (patch.case !== undefined) {
    put(SPACE_QUERY.case, isCaseId(patch.case) ? patch.case : null);
  }
  Object.entries(patch.extra ?? {}).forEach(([name, value]) => {
    put(name, value);
  });
  return spacePath(
    here.workspaceId,
    patch.ref ?? here.ref,
    patch.tab ?? here.tab,
    next.toString(),
  );
};
