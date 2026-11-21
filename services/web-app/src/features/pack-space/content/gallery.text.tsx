import type { QueryClient } from "@tanstack/react-query";
import { packStudioKeys } from "@entities/pack-studio";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { GALLERY_WORKSPACE, SpaceGalleryFrame } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import {
  CONTENT_TEXT,
  CONTENT_TEXT_PATH,
  CONTENT_VERSION_DIR,
  RELEASED_MODEL,
  seedContentModel,
  seedContentText,
} from "./fixtures";
import { slots } from "./slots";

// Записи галереи сегмента «Текст» (S8b): замечание с автоисправлением, выпущенная версия, телефон.
const WS = GALLERY_WORKSPACE.id;
const SEARCH = "doc=technical_specification&seg=text";

const TYPO = [
  "% Техническое задание. Раздел «Введение»",
  "\\section{Введение}",
  "",
  "\\subsection{Наименование программы}",
  "Полное наименование: «{{ project.name_ru }}».",
  "Краткое наименование: «{{ meta.name_shrt }}».",
  "",
  "\\subsection{Область применения}",
  "Программа предназначена для {{ project.purpose }}.",
  "",
].join("\n");

const seedTypo = (client: QueryClient) => {
  seedContentText(client);
  for (const lang of ["ru", "en"]) {
    const path = CONTENT_TEXT_PATH.replace(".ru.", `.${lang}.`);
    client.setQueryData(packStudioKeys.file(WS, path), {
      ...CONTENT_TEXT,
      path,
      content: TYPO,
    });
  }
  client.setQueryData(packStudioKeys.lint(WS, CONTENT_VERSION_DIR, "0"), {
    scope: "version",
    target: CONTENT_VERSION_DIR,
    released: false,
    errors: 0,
    warnings: 1,
    findings: [
      {
        severity: "warning",
        check: "outcome",
        message:
          "Шаблон files/technical_specification/technical_specification.tex читает project.meta.name_shrt, а такого поля нет в meta_fields версии: значение всегда пустое.",
        path: CONTENT_TEXT_PATH,
        line: 6,
        pointer: null,
      },
    ],
  });
  client.setQueryData(packStudioKeys.hints(WS, CONTENT_VERSION_DIR), {
    version: CONTENT_VERSION_DIR,
    meta_fields: [
      { key: "name_short", type: "string", label: null, group: null },
    ],
    macros: [],
  });
};

const RELEASED_DIR = CONTENT_VERSION_DIR.replace("2026.1.3", "2026.1.2");

const seedReleased = (client: QueryClient) => {
  seedContentModel(client, RELEASED_MODEL);
  for (const lang of ["ru", "en"]) {
    const path = CONTENT_TEXT_PATH.replace("2026.1.3", "2026.1.2").replace(
      ".ru.",
      `.${lang}.`,
    );
    client.setQueryData(packStudioKeys.file(WS, path), {
      ...CONTENT_TEXT,
      path,
      readOnly: "version_released",
    });
  }
  client.setQueryData(packStudioKeys.lint(WS, RELEASED_DIR, "0"), {
    scope: "version",
    target: RELEASED_DIR,
    released: true,
    errors: 0,
    warnings: 0,
    findings: [],
  });
};

const frameFor = (
  options: { phone?: boolean; version?: string; height: string } = {
    height: "34rem",
  },
) => (
  <SpaceGalleryFrame
    tab="content"
    search={SEARCH}
    {...(options.version ? { version: options.version } : {})}
    height={options.height}
  >
    <SpaceScreen slots={slots} phone={options.phone ?? false} />
  </SpaceGalleryFrame>
);

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_content_text_fix",
    title: "Содержимое, «Текст»: замечание с кнопкой «Исправить»",
    note: "Правка пишется сама через 1,5 секунды. Под редактором ближайшее к курсору замечание; опечатка в поле исправляется одной кнопкой.",
    frame: "screen",
    width: 1280,
    seed: seedTypo,
    render: () => frameFor({ height: "36rem" }),
  },
  {
    id: "sp_content_text_released",
    title: "Содержимое, «Текст»: выпущенная версия",
    note: "Только чтение, рядом «Править копию».",
    frame: "screen",
    width: 1280,
    seed: seedReleased,
    render: () => frameFor({ version: "2026.1.2", height: "36rem" }),
  },
  {
    id: "sp_content_text_phone",
    title: "Содержимое, «Текст»: телефон",
    frame: "plain",
    width: 390,
    seed: seedTypo,
    render: () => frameFor({ phone: true, height: "40rem" }),
  },
];
