import { useEffect } from "react";
import {
  isSpaceTab,
  type PackVersionRef,
  type SpaceTab,
} from "@entities/pack-studio";
import { useSpace } from "./SpaceContext";
import { cleanInputs, readSituation } from "./situation";

// Что Студия помнит о пространстве (pack-studio-ux.md, 4.6): последнее место и мелочи
// интерфейса. Только в браузере и только удобство: без памяти экран открывается с умолчаниями.
// Черновик и изменения живут в клоне на сервере.

export type SpacePlace = {
  ref: PackVersionRef;
  tab: SpaceTab;
  inputs: Record<string, string>;
};
type UiValue = boolean | string | number;
type Stored = { place?: unknown; ui?: Record<string, UiValue> };

const keyOf = (workspaceId: string): string => `ps.space.${workspaceId}`;

// Запасная память на случай, когда хранилище не открывается (частное окно).
const fallback = new Map<string, Stored>();

const isStr = (value: unknown): value is string => typeof value === "string";

const readStored = (workspaceId: string): Stored => {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(keyOf(workspaceId));
  } catch {
    return fallback.get(workspaceId) ?? {};
  }
  try {
    const data: unknown = raw ? JSON.parse(raw) : {};
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
};

const writeStored = (workspaceId: string, data: Stored): void => {
  fallback.set(workspaceId, data);
  try {
    window.localStorage.setItem(keyOf(workspaceId), JSON.stringify(data));
  } catch {
    // Память не открылась: остаётся запасная, на время вкладки.
  }
};

const isRef = (value: unknown): value is PackVersionRef =>
  typeof value === "object" &&
  value !== null &&
  ["pack", "template", "version"].every((key) =>
    isStr((value as Record<string, unknown>)[key]),
  );

/** Последнее место в пространстве; повреждённая запись считается отсутствующей. */
export const readPlace = (workspaceId: string): SpacePlace | null => {
  const place = readStored(workspaceId).place;
  if (typeof place !== "object" || place === null) return null;
  const { ref, tab, inputs } = place as Record<string, unknown>;
  if (!isRef(ref) || !isSpaceTab(isStr(tab) ? tab : undefined)) return null;
  const pairs =
    typeof inputs === "object" && inputs !== null
      ? Object.entries(inputs).filter((pair): pair is [string, string] =>
          isStr(pair[1]),
        )
      : [];
  return { ref, tab: tab as SpaceTab, inputs: cleanInputs(pairs) };
};

export const writePlace = (workspaceId: string, place: SpacePlace): void => {
  writeStored(workspaceId, { ...readStored(workspaceId), place });
};

/** Мелочи интерфейса пространства: раскрыто ли «Ещё N условий», скрытые части и так далее. */
export const readUi = (workspaceId: string, key: string): UiValue | undefined =>
  readStored(workspaceId).ui?.[key];

export const writeUi = (
  workspaceId: string,
  key: string,
  value: UiValue,
): void => {
  const stored = readStored(workspaceId);
  writeStored(workspaceId, { ...stored, ui: { ...stored.ui, [key]: value } });
};

/** Запоминает место (версия, вкладка, условия студента) при каждой его смене. */
export const useRememberPlace = (): void => {
  const { workspace, versionRef, tab, location } = useSpace();
  const inputsKey = JSON.stringify(readSituation(location.search).inputs);
  useEffect(() => {
    writePlace(workspace.id, {
      ref: versionRef,
      tab,
      inputs: JSON.parse(inputsKey) as Record<string, string>,
    });
  }, [workspace.id, versionRef, tab, inputsKey]);
};
