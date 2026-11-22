import type { QueryClient } from "@tanstack/react-query";
import { packOutcomeKeys, packStudioKeys } from "@entities/pack-studio";
import { explainFor } from "@entities/pack-studio/reference";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { slots as contentSlots } from "../content/slots";
import { SAMPLE_PDF_URL } from "../content/signatures/samplePdf";
import { seedContentModel, seedContentText } from "../content/fixtures";
import { GALLERY_WORKSPACE, SpaceGalleryFrame } from "../galleryKit";
import { slots as detailsSlots } from "../details/slots";
import { slots as resultSlots } from "../result/slots";
import { SpaceScreen } from "../shell/SpaceScreen";
import { mergeSpaceSlots } from "../shell/spaceSlots";
import {
  PV_DOC,
  PV_OFF_DOC,
  PV_REF,
  buildKeyFor,
  previewBuild,
  previewOptions,
  previewOutcome,
  seedPreview,
  type PreviewSeed,
} from "./fixtures";
import { slots as previewSlots } from "./slots";
import { seedPreviewBuild } from "./buildSeed";
import { findingsSeed } from "./galleryFindings";

// Записи галереи предпросмотра PDF (S9): «Содержимое» с готовой страницей и замечаниями, документ
// не в комплекте, сборка не удалась, страница устарела, раздел без документа, «Результат» с
// предпросмотром в «Подробностях», телефон. Страница-образец лежит в записи, сервера нет.

const WS = GALLERY_WORKSPACE.id;
const contentScreen = mergeSpaceSlots([
  ["content", contentSlots],
  ["preview", previewSlots],
]);
const resultScreen = mergeSpaceSlots([
  ["result", resultSlots],
  ["details", detailsSlots],
]);

const DOC = `doc=${PV_DOC}&seg=text`;

const seedContent = (
  client: QueryClient,
  options: {
    search?: string;
    built?: PreviewSeed["built"];
    findings?: boolean;
  } = {},
) => {
  seedContentText(client);
  seedContentModel(client);
  seedPreview(client, {
    search: options.search ?? "",
    built: options.built ?? { pdfUrl: SAMPLE_PDF_URL },
  });
  if (options.findings !== false) findingsSeed(client);
};

const frame = (
  search: string,
  options: {
    tab?: "content" | "result";
    phone?: boolean;
    height?: string;
  } = {},
) => (
  <SpaceGalleryFrame
    tab={options.tab ?? "content"}
    search={search}
    height={options.height ?? "50rem"}
  >
    <SpaceScreen
      slots={options.tab === "result" ? resultScreen : contentScreen}
      phone={options.phone ?? false}
    />
  </SpaceGalleryFrame>
);

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_preview_content",
    title:
      "Предпросмотр PDF в «Содержимом»: готовая страница и замечания к файлу",
    note: "Справа условия студента, пример данных и страница. Под ней замечания к файлу: «Строка N» прокручивает редактор.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContent(client);
    },
    render: () => frame(DOC),
  },
  {
    id: "sp_preview_stale",
    title: "Предпросмотр PDF: после смены условия страница устарела",
    note: "Сборка стартовала при других условиях: плашка «соберите заново» и главная кнопка. Сам предпросмотр заново не собирается.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContent(client);
      // Страница собрана при условиях по умолчанию, а на экране вид работы «Исследовательская».
      const build = previewBuild();
      seedPreview(client, { search: "i.kind=research", built: null });
      client.setQueryData(packStudioKeys.previewBuild(WS, build.id), build);
      seedPreviewBuild(WS, PV_REF, PV_DOC, {
        buildId: build.id,
        key: buildKeyFor(PV_DOC, previewOutcome(), previewOptions(), null),
        pdfUrl: SAMPLE_PDF_URL,
      });
    },
    render: () => frame(`${DOC}&i.kind=research`),
  },
  {
    id: "sp_preview_not_in_kit",
    title: "Предпросмотр PDF: документа нет в комплекте при этих условиях",
    note: "Страницы нет, и сказано почему. «Сбросить условия» возвращает умолчания.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContent(client, { built: null, findings: false });
    },
    render: () => frame(`doc=${PV_OFF_DOC}&seg=text`, { height: "40rem" }),
  },
  {
    id: "sp_preview_failed",
    title: "Предпросмотр PDF: сборка не удалась",
    note: "Причина человеческим языком, «Собрать ещё раз» и журнал.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContent(client, {
        built: {
          build: previewBuild("failed", {
            finished_at: "2026-11-14T09:30:09Z",
            pages: null,
            error: { code: "build_failed", detail: null },
          }),
        },
      });
    },
    render: () => frame(DOC),
  },
  {
    id: "sp_preview_no_document",
    title: "Предпросмотр PDF: у раздела формы страницы нет",
    note: "Правая колонка у раздела формы не рисуется совсем: форма получает всю ширину, заглушки «Выберите документ» нет.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContent(client, { built: null, findings: false });
    },
    render: () => frame("part=fields", { height: "30rem" }),
  },
  {
    id: "sp_preview_result",
    title: "«Результат»: предпросмотр PDF внутри «Подробностей»",
    note: "Кнопка «PDF» в строке документа выбирает его и открывает предпросмотр справа. Условия те же, что на экране.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedPreview(client, { built: { pdfUrl: SAMPLE_PDF_URL } });
      const outcome = previewOutcome();
      const element = { section: "documents", id: PV_DOC } as const;
      const data = explainFor(outcome, element, "coursework");
      if (data) {
        client.setQueryData(
          packOutcomeKeys.explain(WS, PV_REF, {
            state: "work_tree",
            scenario: null,
            example: null,
            inputs: {},
            element,
          }),
          { data, etag: null },
        );
      }
    },
    render: () =>
      frame(`sel=documents%3A${PV_DOC}&preview=1`, {
        tab: "result",
        height: "56rem",
      }),
  },
  {
    id: "sp_preview_phone",
    title: "Предпросмотр PDF в «Подробностях»: телефон",
    frame: "plain",
    width: 390,
    seed: (client) => {
      seedPreview(client, { built: { pdfUrl: SAMPLE_PDF_URL } });
    },
    render: () =>
      frame(`sel=documents%3A${PV_DOC}&preview=1`, {
        tab: "result",
        phone: true,
        height: "56rem",
      }),
  },
];
