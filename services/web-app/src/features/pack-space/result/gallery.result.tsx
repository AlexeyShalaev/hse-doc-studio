import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  type PackOutcome,
  type PackOutcomeInputs,
  type PackOutcomeRequest,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
  VKR_INPUTS,
  VKR_OUTCOME,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import {
  GALLERY_REF,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { setOpenParts } from "./partsStore";
import { PART_IDS, type PartId } from "./model";
import { slots } from "./slots";

// Галерея центра «Результата» на эталонах контракта (`/dev/server-screens`): документы курсового
// проекта и ВКР с NDA. Сервер не нужен: результат и условия лежат в кэше запросов записи.

const ID = GALLERY_WORKSPACE.id;

export type ResultKind = "ready" | "loading" | "error" | "empty";
type Work = "coursework" | "vkr";

export type ResultSeed = {
  work?: Work;
  kind?: ResultKind;
  /** Query адреса: условия студента `i.nda=yes`, выбранная строка `sel=...`. */
  search?: string;
  /** Раскрытые части; по умолчанию только «Документы». */
  open?: readonly PartId[] | null;
  /** Раскрыть «Не вошло» во всех частях. */
  missing?: boolean;
};

const MISSING_NAMES = [
  "sp-docs-missing",
  "sp-data-missing",
  "sp-people-missing",
  "sp-deadlines-missing",
  "sp-signatures-missing",
];

const requestOf = (search: string): PackOutcomeRequest => {
  const inputs: Record<string, string> = {};
  new URLSearchParams(search).forEach((value, name) => {
    if (name.startsWith("i.")) inputs[name.slice(2)] = value;
  });
  return { state: "work_tree", inputs };
};

const failure = (client: QueryClient, key: readonly unknown[]): void => {
  client
    .getQueryCache()
    .build(client, { queryKey: key })
    .setState({
      status: "error",
      fetchStatus: "idle",
      data: undefined,
      error: new ApiError("Внутренняя ошибка.", "internal_error", 500),
      errorUpdateCount: 1,
      errorUpdatedAt: Date.now(),
    });
};

/** Заполняет кэш запросов записи: результат, условия версии и память раскрытых частей. */
export const seedResult = (
  client: QueryClient,
  {
    work = "coursework",
    kind = "ready",
    search = "",
    open = ["documents"],
    missing = false,
  }: ResultSeed = {},
): void => {
  const request = requestOf(search);
  const ref = GALLERY_REF;
  client.setQueryDefaults(packOutcomeKeys.all(ID), {
    retryOnMount: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });
  const base: PackOutcome = structuredClone(
    work === "coursework" ? COURSEWORK_OUTCOME : VKR_OUTCOME,
  );
  const inputsBase: PackOutcomeInputs =
    work === "coursework" ? COURSEWORK_INPUTS : VKR_INPUTS;
  const outcome: PackOutcome = {
    ...base,
    workspace_id: ID,
    inputs: { ...base.inputs, ...request.inputs },
  };
  client.setQueryData(packOutcomeKeys.inputs(ID, ref, "work_tree"), {
    ...inputsBase,
    workspace_id: ID,
  });
  const key = packOutcomeKeys.result(ID, ref, request);
  if (kind === "ready") client.setQueryData(key, outcome);
  else if (kind === "empty") {
    client.setQueryData(key, {
      ...outcome,
      documents: [],
      meta: [],
      forms: [],
      participants: [],
      points: [],
      trace: [],
    });
  } else if (kind === "loading") {
    void client.prefetchQuery({
      queryKey: key,
      queryFn: () => new Promise<PackOutcome>(() => undefined),
    });
  } else failure(client, key);
  // Раскрытые части и списки «Не вошло» живут в хранилище клиента запросов этой записи.
  if (open !== null) {
    setOpenParts(client, ID, open, missing ? MISSING_NAMES : []);
  }
};

const Screen = ({
  search,
  phone = false,
  height,
}: {
  search?: string;
  phone?: boolean;
  height?: string;
}) => (
  <SpaceGalleryFrame
    tab="result"
    {...(search === undefined ? {} : { search })}
    {...(height === undefined ? {} : { height })}
  >
    <SpaceScreen slots={slots} phone={phone} />
  </SpaceGalleryFrame>
);

const ALL: readonly PartId[] = PART_IDS;

type Entry = {
  id: string;
  title: string;
  note: string;
  seed: ResultSeed;
  search?: string;
  phone?: boolean;
};

const ENTRIES: Entry[] = [
  {
    id: "sp_result_desktop",
    title: "Результат: документы курсового проекта, выбран документ",
    note: "Оглавление слева, заголовок «Студент получит N документов», части результата, выбранная строка подсвечена.",
    search: "sel=documents%3Areport",
    seed: { search: "sel=documents%3Areport" },
  },
  {
    id: "sp_result_all_parts",
    title: "Результат: все части раскрыты",
    note: "Данные проекта по группам, участники, точки сдачи с сроками, подписи по порядку.",
    seed: { open: ALL },
  },
  {
    id: "sp_result_missing",
    title: "Результат: «Не вошло» с причинами (ВКР с NDA)",
    note: "У каждой строки причина простыми словами и кнопка «Показать при …», которая ставит условие.",
    seed: { work: "vkr", open: ALL, missing: true },
  },
  {
    id: "sp_result_many",
    title: "Результат: больше десяти документов, есть поиск и фильтр",
    note: "ВКР: 18 документов, группы ЕСПД, отчёт, практика, презентации.",
    seed: { work: "vkr" },
  },
  {
    id: "sp_result_loading",
    title: "Результат: считаю",
    note: "Первый расчёт ещё не пришёл.",
    seed: { kind: "loading" },
  },
  {
    id: "sp_result_error",
    title: "Результат: не удалось посчитать",
    note: "Причина и «Повторить».",
    seed: { kind: "error" },
  },
  {
    id: "sp_result_empty",
    title: "Результат: в версии нет документов",
    note: "Пустое состояние объясняет и ничего не предлагает лишнего.",
    seed: { kind: "empty" },
  },
  {
    id: "sp_result_phone",
    title: "Результат на телефоне",
    note: "Слева ничего: части сворачиваются в центре, у строки одна кнопка.",
    phone: true,
    seed: { work: "vkr", open: ["documents"] },
  },
  {
    id: "sp_result_phone_missing",
    title: "Телефон: «Не вошло» раскрыто",
    note: "Причина под названием, кнопка «Показать при …» на всю строку.",
    phone: true,
    seed: { work: "vkr", open: ["documents"], missing: true },
  },
];

export const galleryEntries: GalleryEntry[] = ENTRIES.map((entry) => ({
  id: entry.id,
  title: entry.title,
  note: entry.note,
  frame: entry.phone ? "plain" : "screen",
  width: entry.phone ? 390 : 1280,
  seed: (client) => {
    seedResult(client, entry.seed);
  },
  render: () => (
    <Screen
      {...(entry.search === undefined ? {} : { search: entry.search })}
      {...(entry.phone
        ? { phone: true, height: "46rem" }
        : { height: "46rem" })}
    />
  ),
}));
