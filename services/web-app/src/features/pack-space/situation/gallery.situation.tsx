import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  type PackOutcomeInputs,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  COURSEWORK_COMPARE,
  COURSEWORK_INPUTS,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import {
  GALLERY_REF,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { defineSpaceSlots } from "../shell/spaceSlots";
import { deltaStore } from "./deltaStore";
import SituationTop from "./SituationTop";

// Полоса «Для какого студента» на фикстурах контракта (курсовой проект): сервер не нужен.
// Плашка «что изменилось» берёт сравнение из кэша записи; сама запись помнит прежнее состояние
// в `deltaStore` (на странице галереи одна запись такого рода, поэтому адрес у них общий).

const ID = GALLERY_WORKSPACE.id;
const SLOTS = defineSpaceSlots({
  mainTop: { result: SituationTop },
  main: {
    result: () => (
      <p style={{ color: "var(--fg-2)", fontSize: "0.8125rem", margin: 0 }}>
        Центр результата (S6)
      </p>
    ),
  },
});
const SCOPE = `${ID}/${GALLERY_REF.pack}/${GALLERY_REF.template}/${GALLERY_REF.version}`;
const AFTER = { supervisor: "company" };

type Mode = "ready" | "loading" | "error" | "none";

const seedOf =
  (mode: Mode = "ready", delta = false, ref: PackVersionRef = GALLERY_REF) =>
  (client: QueryClient) => {
    client.setQueryDefaults(packOutcomeKeys.all(ID), {
      retryOnMount: false,
      refetchOnMount: false,
      refetchOnReconnect: false,
      refetchOnWindowFocus: false,
    });
    const inputsKey = packOutcomeKeys.inputs(ID, ref, "work_tree");
    if (mode === "loading") {
      void client.prefetchQuery({
        queryKey: inputsKey,
        queryFn: () => new Promise<PackOutcomeInputs>(() => undefined),
      });
    } else if (mode === "error") {
      client
        .getQueryCache()
        .build(client, { queryKey: inputsKey })
        .setState({
          status: "error",
          fetchStatus: "idle",
          data: undefined,
          error: new ApiError("Внутренняя ошибка.", "internal_error", 500),
          errorUpdateCount: 1,
          errorUpdatedAt: Date.now(),
        });
    } else {
      client.setQueryData(inputsKey, {
        ...COURSEWORK_INPUTS,
        workspace_id: ID,
        ...(mode === "none" ? { inputs: [], defaults: {} } : {}),
      });
    }
    client.setQueryData(
      packOutcomeKeys.scenarios(ID, ref.pack, ref.template, "work_tree"),
      { ...COURSEWORK_SCENARIOS, workspace_id: ID },
    );
    client.setQueryData(
      packOutcomeKeys.scenarioRun(
        ID,
        ref,
        "work_tree",
        COURSEWORK_INPUTS.revision,
      ),
      COURSEWORK_RUN,
    );
    if (delta) {
      client.setQueryData(
        packOutcomeKeys.compare(ID, ref, {
          left: { state: "work_tree", inputs: {} },
          right: { state: "work_tree", inputs: AFTER },
        }),
        { data: COURSEWORK_COMPARE, etag: null },
      );
      deltaStore.record({
        scope: SCOPE,
        before: { inputs: {}, caseId: null },
        after: { inputs: AFTER, caseId: null },
        label: "Научный руководитель: Из компании",
      });
    }
  };

const entry = (
  id: string,
  title: string,
  note: string,
  search: string,
  options: {
    mode?: Mode;
    delta?: boolean;
    width?: number;
    phone?: boolean;
    version?: string;
  } = {},
): GalleryEntry => ({
  id,
  title,
  note,
  frame: options.phone ? "plain" : "screen",
  width: options.width ?? 1280,
  seed: seedOf(
    options.mode,
    options.delta,
    options.version
      ? { ...GALLERY_REF, version: options.version }
      : GALLERY_REF,
  ),
  render: () => (
    <SpaceGalleryFrame
      search={search}
      height={options.phone ? "26rem" : "17rem"}
      {...(options.version ? { version: options.version } : {})}
    >
      <SpaceScreen slots={SLOTS} phone={options.phone ?? false} />
    </SpaceGalleryFrame>
  ),
});

export const galleryEntries: GalleryEntry[] = [
  entry(
    "sp_sit_default",
    "Для какого студента: по умолчанию",
    "Три главных условия кнопками (по числу правил, которые их читают), «Ещё N условий», «Готовые случаи» и меню «Ещё».",
    "",
  ),
  entry(
    "sp_sit_changed",
    "Изменённое условие и случай",
    "Изменённое условие с акцентной рамкой; выбран готовый случай (его название на кнопке).",
    "case=company-supervisor&i.kind=research",
  ),
  entry(
    "sp_sit_delta",
    "Плашка «что изменилось»",
    "После смены условия: сколько добавилось, изменилось и убралось по разделам (данные сравнения с сервера).",
    "i.supervisor=company",
    { delta: true },
  ),
  entry(
    "sp_sit_delta_only",
    "«Показать только изменившееся» включено",
    "Кнопка меняется на «Показать всё»; строки результата получают фильтр и подсветку из useSituationDelta.",
    "i.supervisor=company&delta=1",
    { delta: true },
  ),
  entry(
    "sp_sit_released",
    "Выпущенная версия",
    "Над полосой плашка «версия выпущена и не меняется»; условия по-прежнему можно примерять.",
    "",
    { version: "2026.1.2" },
  ),
  entry(
    "sp_sit_loading",
    "Условия загружаются",
    "Пока ответ не пришёл: три серых кнопки.",
    "",
    { mode: "loading" },
  ),
  entry(
    "sp_sit_error",
    "Условия не загрузились",
    "Одна строка и «Повторить».",
    "",
    { mode: "error" },
  ),
  entry(
    "sp_sit_none",
    "У шаблона нет условий",
    "Пустое состояние: причина без кнопок.",
    "",
    { mode: "none" },
  ),
  entry(
    "sp_sit_phone",
    "Телефон: ряд прокручивается",
    "Кнопки в одну строку с горизонтальной прокруткой; «Ещё условий», случаи и меню открываются шторкой.",
    "i.supervisor=company",
    { phone: true, width: 390, delta: true },
  ),
];
