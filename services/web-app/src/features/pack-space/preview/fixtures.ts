import type { QueryClient } from "@tanstack/react-query";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackOutcome,
  type PackOutcomeRequest,
  type PackPreviewBuild,
  type PackPreviewOptions,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  COURSEWORK_INPUTS,
  COURSEWORK_OUTCOME,
} from "@entities/pack-studio/reference";
import {
  filesKeyOf,
  previewTarget,
  runKeyOf,
  INPUTS_SOURCE,
} from "@features/pack-outcome/lib/previewRequest";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../galleryKit";
import { seedPreviewBuild } from "./buildSeed";

// Фикстуры предпросмотра для записей галереи и тестов: результат курсового проекта с документами
// «Содержимого» (Техническое задание в комплекте, NDA нет), параметры сборки и готовая сборка.
// Всё лежит в кэше запросов, как будто сервер уже ответил.

const WS = GALLERY_WORKSPACE.id;
export const PV_REF: PackVersionRef = GALLERY_REF;
export const PV_DOC = "technical_specification";
export const PV_VARIANT_DOC = "test_program_and_methodology";
export const PV_OFF_DOC = "nda";
export const PV_BUILD_ID = "b1c2d3e4-0000-4000-8000-0000000000a9";

const report = COURSEWORK_OUTCOME.documents.find((doc) => doc.id === "report");
if (!report) throw new Error("в эталоне нет документа report");

/** Результат «Содержимого»: ТЗ в комплекте, NDA выключен (его нет при этих условиях). */
export const previewOutcome = (): PackOutcome => ({
  ...structuredClone(COURSEWORK_OUTCOME),
  workspace_id: WS,
  documents: [
    {
      ...report,
      id: PV_DOC,
      name: { ru: "Техническое задание", en: "Statement of Work" },
      variants: [],
    },
    {
      ...report,
      id: PV_VARIANT_DOC,
      name: { ru: "Программа и методика испытаний", en: "Test Program" },
      variants: [],
    },
    {
      ...report,
      id: "presentation",
      name: { ru: "Презентация защиты", en: "Defence Slides" },
      variants: [],
    },
    {
      ...report,
      id: PV_OFF_DOC,
      name: { ru: "Соглашение о неразглашении", en: "NDA" },
      state: "inactive",
      why: [],
      variants: [],
    },
  ],
});

export const previewOptions = (
  ref: PackVersionRef = PV_REF,
): PackPreviewOptions => ({
  workspace_id: WS,
  pack: ref.pack,
  template: ref.template,
  version: ref.version,
  pack_id: ref.pack,
  template_id: ref.template,
  version_id: ref.version,
  documents: [
    {
      id: PV_DOC,
      name: { ru: "Техническое задание", en: "Statement of Work" },
      kinds: [],
      staffing: [],
    },
    {
      id: PV_VARIANT_DOC,
      name: { ru: "Программа и методика испытаний", en: "Test Program" },
      kinds: [],
      staffing: [],
      variants: [
        {
          id: "main",
          label: { ru: "Основной", en: "Main" },
          langs: [],
          pdf: true,
        },
        {
          id: "slides",
          label: { ru: "Слайды", en: "Slides" },
          langs: [],
          pdf: false,
        },
      ],
      default_variant: "main",
    },
  ],
  switches: [
    {
      id: "kind",
      values: ["project", "research"],
      default: "project",
      label: null,
    },
  ],
  examples: [
    {
      id: "auto:normal",
      source: "auto",
      label: null,
      error: null,
      defaults: {},
    },
    {
      id: "long_names",
      source: "file",
      label: { ru: "Длинные ФИО", en: "Long names" },
      error: null,
      defaults: {},
    },
    {
      id: "broken",
      source: "file",
      label: { ru: "Сломанный пример", en: "Broken sample" },
      error: "строка 3: ожидался ключ",
      defaults: {},
    },
  ],
  default_example: "auto:normal",
  combination: {},
});

export const previewBuild = (
  status: PackPreviewBuild["status"] = "succeeded",
  fields: Partial<PackPreviewBuild> = {},
): PackPreviewBuild => ({
  id: PV_BUILD_ID,
  workspace_id: WS,
  pack: PV_REF.pack,
  template: PV_REF.template,
  version: PV_REF.version,
  document: PV_DOC,
  example: "auto:normal",
  combination: { lang: "ru" },
  key: "k",
  status,
  cached: false,
  created_at: "2026-11-14T09:30:00Z",
  started_at: "2026-11-14T09:30:01Z",
  finished_at: status === "succeeded" ? "2026-11-14T09:30:09Z" : null,
  pages: 3,
  error: null,
  source_file: null,
  has_anchors: false,
  ...fields,
});

/** Запрос результата, как его строит экран по адресу (условия `i.*`, пример `example`). */
export const outcomeRequestOf = (search: string): PackOutcomeRequest => {
  const params = new URLSearchParams(search);
  const inputs: Record<string, string> = {};
  params.forEach((value, name) => {
    if (name.startsWith("i.")) inputs[name.slice(2)] = value;
  });
  return {
    state: "work_tree",
    scenario: null,
    example: params.get("example"),
    inputs,
  };
};

/** Ключ запроса сборки, какой посчитает экран для этого адреса (чтобы подложить готовую сборку). */
export const buildKeyFor = (
  doc: string,
  outcome: PackOutcome,
  options: PackPreviewOptions,
  example: string | null,
): string => {
  const target = previewTarget({
    options,
    document: doc,
    source: INPUTS_SOURCE,
    variantPick: null,
    inputs: outcome.inputs,
    example,
    shownExample: outcome.example,
    scenarioLang: undefined,
  });
  return runKeyOf(
    target,
    filesKeyOf({
      revision: outcome.revision,
      scenarioEtag: "",
      filesRevision: 0,
    }),
  );
};

export type PreviewSeed = {
  /** Query адреса: условия `i.*` и пример `example`. */
  search?: string;
  /** Сборка уже готова (страница в записи); `null`: ничего не подложено, соберёт сам экран. */
  built?: { build?: PackPreviewBuild; pdfUrl?: string } | null;
  /** Версия, у которой лежат данные (по умолчанию черновик 2026.1.3). */
  ref?: PackVersionRef;
};

/**
 * Всё, что предпросмотр берёт у сервера, в кэше запросов: результат для условий адреса, условия
 * версии, параметры сборки и, если нужно, готовая сборка.
 */
export const seedPreview = (
  client: QueryClient,
  { search = "", built = null, ref = PV_REF }: PreviewSeed = {},
): void => {
  const outcome = previewOutcome();
  const request = outcomeRequestOf(search);
  const withInputs: PackOutcome = {
    ...outcome,
    inputs: { ...outcome.inputs, ...request.inputs },
    ...(request.example ? { example: request.example } : {}),
  };
  const options = { ...previewOptions(ref) };
  client.setQueryData(packOutcomeKeys.result(WS, ref, request), withInputs);
  client.setQueryData(packOutcomeKeys.inputs(WS, ref, "work_tree"), {
    ...COURSEWORK_INPUTS,
    workspace_id: WS,
  });
  client.setQueryData(packStudioKeys.previewOptions(WS, ref), options);
  seedPreviewBuild(WS, ref, PV_DOC, null);
  if (built) {
    const build = built.build ?? previewBuild();
    client.setQueryData(packStudioKeys.previewBuild(WS, build.id), build);
    seedPreviewBuild(WS, ref, PV_DOC, {
      buildId: build.id,
      key: buildKeyFor(PV_DOC, withInputs, options, request.example ?? null),
      ...(built.pdfUrl ? { pdfUrl: built.pdfUrl } : {}),
    });
  }
};
