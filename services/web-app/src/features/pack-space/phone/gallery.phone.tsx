import type { QueryClient } from "@tanstack/react-query";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { packStudioKeys } from "@entities/pack-studio";
import { referenceModel } from "@entities/pack-studio/reference";
import { galleryEntries as changesEntries } from "../changes/gallery.changes";
import { galleryEntries as detailsEntries } from "../details/gallery.details";
import { seedContentModel, seedContentText } from "../content/fixtures";
import {
  GALLERY_REF,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { seedNav } from "../nav/fixtures";
import { seedResult } from "../result/gallery.result";
import { SpaceScreen } from "../shell/SpaceScreen";
import { seedLint } from "../check/seeds";
import { seedPreview } from "../preview/fixtures";
import { SAMPLE_PDF_URL } from "../content/signatures/samplePdf";

// Записи галереи области «Телефон»: экран пространства целиком (настоящие слоты всех областей) в
// ширине 390 px. Данные лежат в кэше запросов, сервера нет. Каждая запись проходит тот же путь,
// что человек: открыл, документ, шторка, правка условий, «Содержимое», «Проверка», «Изменения».

const seedChanges = (client: QueryClient): void => {
  changesEntries.find((entry) => entry.id === "sp_ch_ready")?.seed?.(client);
};

const seedDetailsOf = (client: QueryClient): void => {
  detailsEntries
    .find((entry) => entry.id === "sp_details_phone")
    ?.seed?.(client);
};

/** Общее для всех экранов: полосы, «Изменения», результат ВКР, «почему так» выбранного документа. */
const seedBase = (client: QueryClient): void => {
  seedNav(["x"])(client);
  seedChanges(client);
  seedResult(client, { work: "vkr", open: ["documents"] });
  seedDetailsOf(client);
  seedLint(client, "normal");
};

const seedContent = (client: QueryClient): void => {
  seedContentText(client);
  seedContentModel(client);
  seedPreview(client, { built: { pdfUrl: SAMPLE_PDF_URL } });
};

const seedEdit = (client: QueryClient): void => {
  client.setQueryData(
    packStudioKeys.model(GALLERY_WORKSPACE.id, GALLERY_REF),
    referenceModel(
      GALLERY_WORKSPACE.id,
      "hse-cs-se",
      "vkr",
      GALLERY_REF.version,
    ),
  );
};

type Spec = {
  id: string;
  title: string;
  note: string;
  tab?: "result" | "content" | "check";
  search?: string;
  height?: string;
  seed?: (client: QueryClient) => void;
};

const phone = (spec: Spec): GalleryEntry => ({
  id: spec.id,
  title: spec.title,
  note: spec.note,
  frame: "plain",
  width: 390,
  seed: (client) => {
    seedBase(client);
    spec.seed?.(client);
  },
  render: () => (
    <SpaceGalleryFrame
      tab={spec.tab ?? "result"}
      search={spec.search ?? ""}
      height={spec.height ?? "52rem"}
    >
      <SpaceScreen phone />
    </SpaceGalleryFrame>
  ),
});

export const galleryEntries: GalleryEntry[] = [
  phone({
    id: "sp_phone_result",
    title: "Телефон: «Результат»",
    note: "Две полосы сверху, «Для какого студента» рядом, части результата, внизу четыре вкладки.",
  }),
  phone({
    id: "sp_phone_details",
    title: "Телефон: «Подробности» шторкой",
    note: "Строка документа выбрана: шторка над нижними вкладками.",
    search: "sel=documents%3Atechnical_specification",
  }),
  phone({
    id: "sp_phone_changes",
    title: "Телефон: «Изменения» страницей",
    note: "Страница с кнопкой отправки внизу, нижние вкладки на месте.",
    search: "changes=1",
  }),
  phone({
    id: "sp_phone_content",
    title: "Телефон: «Содержимое»",
    note: "Список разделов страницей первого уровня.",
    tab: "content",
    seed: seedContent,
  }),
  phone({
    id: "sp_phone_content_doc",
    title: "Телефон: документ в «Содержимом»",
    note: "Правка документа следующей страницей, «Предпросмотр PDF» в шапке документа.",
    tab: "content",
    search: "doc=technical_specification&seg=text",
    seed: seedContent,
  }),
  phone({
    id: "sp_phone_check",
    title: "Телефон: «Проверка»",
    note: "Части переключаются полосой над заголовком.",
    tab: "check",
  }),
  phone({
    id: "sp_phone_edit",
    title: "Телефон: правка условия",
    note: "Форма во всю ширину шторки.",
    search: "sel=documents%3Atechnical_specification",
    seed: seedEdit,
  }),
];
