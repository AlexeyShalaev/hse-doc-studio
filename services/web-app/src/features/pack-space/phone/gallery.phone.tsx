import type { QueryClient } from "@tanstack/react-query";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { packStudioKeys } from "@entities/pack-studio";
import { referenceModel } from "@entities/pack-studio/reference";
import { galleryEntries as changesEntries } from "../changes/gallery.changes";
import { galleryEntries as detailsEntries } from "../details/gallery.details";
import { galleryEntries as partEntries } from "../content/gallery.parts";
import { galleryEntries as signatureEntries } from "../content/gallery.signatures";
import {
  CONTENT_TEXT_PATH,
  seedContentModel,
  seedContentText,
} from "../content/fixtures";
import { SIGNATURES_DOC } from "../content/signatures/fixtures";
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

/** Данные записи другой области по её id: разделы версии и «Подписи» кладут своё в кэш сами. */
const seedOf =
  (entries: GalleryEntry[], id: string) =>
  (client: QueryClient): void => {
    entries.find((entry) => entry.id === id)?.seed?.(client);
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
  /** Планшет: ширина 820 px, раскладка десктопа с выезжающей правой колонкой. */
  tablet?: boolean;
};

const phone = (spec: Spec): GalleryEntry => ({
  id: spec.id,
  title: spec.title,
  note: spec.note,
  frame: spec.tablet ? "screen" : "plain",
  width: spec.tablet ? 820 : 390,
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
      <SpaceScreen phone={!spec.tablet} />
    </SpaceGalleryFrame>
  ),
});

export const galleryEntries: GalleryEntry[] = [
  phone({
    id: "sp_phone_tablet_details",
    title: "Планшет: «Подробности» выезжают справа",
    note: "820 px: левая колонка 200 px, подробности поверх, закрываются крестиком.",
    search: "sel=documents%3Atechnical_specification",
    tablet: true,
    height: "46rem",
  }),
  phone({
    id: "sp_phone_tablet_preview",
    title: "Планшет: предпросмотр PDF из «Содержимого»",
    note: "Кнопка «Предпросмотр PDF» в шапке документа выдвигает правую колонку.",
    tab: "content",
    search: "doc=technical_specification&seg=text&preview=1",
    seed: seedContent,
    tablet: true,
    height: "46rem",
  }),
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
    id: "sp_phone_terms",
    title: "Телефон: «Условия» документа",
    note: "Форма документа во всю ширину, поля 16 px.",
    tab: "content",
    search: "doc=technical_specification&seg=terms",
    seed: seedContent,
  }),
  phone({
    id: "sp_phone_signatures",
    title: "Телефон: «Подписи» документа",
    note: "Страница PDF с местами подписей и карточки под ней.",
    tab: "content",
    search: `doc=${SIGNATURES_DOC}&seg=signatures`,
    seed: seedOf(signatureEntries, "sp_content_signatures"),
    height: "56rem",
  }),
  phone({
    id: "sp_phone_forms",
    title: "Телефон: раздел «Анкеты»",
    note: "Форма версии без вкладок, на всю ширину.",
    tab: "content",
    search: "part=forms",
    seed: seedOf(partEntries, "sp_content_part_forms"),
  }),
  phone({
    id: "sp_phone_deadlines",
    title: "Телефон: раздел «Сроки и сдача»",
    note: "Профили сдачи и порядок подписания.",
    tab: "content",
    search: "part=deadlines",
    seed: seedOf(partEntries, "sp_content_part_deadlines"),
  }),
  phone({
    id: "sp_phone_files",
    title: "Телефон: «Все файлы»",
    note: "Дерево компактно сверху, файл под ним.",
    tab: "content",
    search: `part=files&file=${encodeURIComponent(CONTENT_TEXT_PATH)}`,
    seed: seedOf(partEntries, "sp_content_files"),
    height: "56rem",
  }),
  phone({
    id: "sp_phone_preview",
    title: "Телефон: предпросмотр PDF из «Содержимого»",
    note: "Кнопка «Предпросмотр PDF» в шапке документа открывает ту же панель шторкой.",
    tab: "content",
    search: "doc=technical_specification&seg=text&preview=1",
    seed: seedContent,
    height: "56rem",
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
