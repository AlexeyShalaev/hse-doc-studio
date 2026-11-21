import type { QueryClient } from "@tanstack/react-query";
import {
  packStudioKeys,
  type PackEditorHints,
  type PackFile,
  type PackLint,
  type PackVersionModel,
} from "@entities/pack-studio";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../galleryKit";

// Фикстуры области для записей галереи и тестов: модель версии 2026.1.3 (черновик) из галереи
// каркаса с восемью документами в трёх группах, текст одного файла и его проверки.

export const CONTENT_VERSION_DIR = `${GALLERY_REF.pack}/templates/${GALLERY_REF.template}/versions/${GALLERY_REF.version}`;

const DOCS: {
  id: string;
  ru: string;
  en: string;
  group: string;
  main: string;
  langs: boolean;
}[] = [
  {
    id: "technical_specification",
    ru: "Техническое задание",
    en: "Statement of Work",
    group: "espd",
    main: "technical_specification.tex",
    langs: true,
  },
  {
    id: "test_program_and_methodology",
    ru: "Программа и методика испытаний",
    en: "Test Program and Methodology",
    group: "espd",
    main: "test_program_and_methodology.tex",
    langs: true,
  },
  {
    id: "source_listing",
    ru: "Текст программы",
    en: "Source Listing",
    group: "espd",
    main: "source_listing.tex",
    langs: true,
  },
  {
    id: "programmer_manual",
    ru: "Руководство программиста",
    en: "Programmer Manual",
    group: "espd",
    main: "programmer_manual.tex",
    langs: true,
  },
  {
    id: "operator_manual",
    ru: "Руководство оператора",
    en: "Operator Manual",
    group: "espd",
    main: "operator_manual.tex",
    langs: true,
  },
  {
    id: "explanatory_note",
    ru: "Пояснительная записка",
    en: "Explanatory Note",
    group: "report",
    main: "explanatory_note.tex",
    langs: true,
  },
  {
    id: "presentation",
    ru: "Презентация защиты",
    en: "Defence Slides",
    group: "pres",
    main: "presentation.pptx",
    langs: false,
  },
  {
    id: "nda",
    ru: "Соглашение о неразглашении",
    en: "NDA",
    group: "nda",
    main: "nda.tex",
    langs: false,
  },
];

const modelFile = (path: string, data: unknown) => ({
  path,
  etag: `etag-${path}`,
  data,
});

export const buildModel = (
  version: string,
  readOnly: PackVersionModel["read_only"],
): PackVersionModel => {
  const dir = `${GALLERY_REF.pack}/templates/${GALLERY_REF.template}/versions/${version}`;
  return {
    workspace_id: GALLERY_WORKSPACE.id,
    pack: GALLERY_REF.pack,
    template: GALLERY_REF.template,
    version,
    read_only: readOnly,
    manifest: modelFile(`${dir}/version.yaml`, {
      id: version,
      langs: ["ru", "en"],
      documents: DOCS.map((doc) => doc.id),
      meta_fields: Object.fromEntries(
        Array.from({ length: 18 }, (_, index) => [
          `field_${String(index)}`,
          {
            type: "string",
            label: {
              ru: `Поле ${String(index)}`,
              en: `Field ${String(index)}`,
            },
            scope: "project",
            required_at: "create",
          },
        ]),
      ),
      forms: [{ id: "project" }, { id: "author" }],
      signatures: {
        slots: Array.from({ length: 6 }, (_, i) => ({
          id: `slot_${String(i)}`,
        })),
      },
      pack_submission: {
        profiles: [{ id: "cp1" }, { id: "cp2" }, { id: "cp3" }],
      },
    }),
    documents: DOCS.map((doc) => {
      const data = {
        name: { ru: doc.ru, en: doc.en },
        group: doc.group,
        required: true,
        scope: "personal",
        supported_kinds: ["project"],
        supported_langs: ["ru", "en"],
        variants: [
          {
            id: "main",
            source_file: `${doc.id}/${doc.main}`,
            engine: "xelatex",
          },
        ],
      };
      return {
        id: doc.id,
        manifest: modelFile(`${dir}/files/${doc.id}/doc.yaml`, data),
        data,
        files: doc.langs
          ? (["ru", "en"] as const).map((lang) => ({
              path: `${doc.id}/${doc.main.replace(/\.tex$/, `.${lang}.tex`)}`,
              bare: `${doc.id}/${doc.main}`,
              lang,
              size: 4096,
            }))
          : [
              {
                path: `${doc.id}/${doc.main}`,
                bare: `${doc.id}/${doc.main}`,
                lang: "",
                size: 4096,
              },
            ],
        references: [],
      };
    }),
    usage: [],
    checks: [],
    problems: [],
    changed: [],
  };
};

export const CONTENT_MODEL = buildModel(GALLERY_REF.version, null);

/** Основной файл «Технического задания» на русском. */
export const CONTENT_TEXT_PATH = `${CONTENT_VERSION_DIR}/files/technical_specification/technical_specification.ru.tex`;

export const CONTENT_TEXT: PackFile = {
  path: CONTENT_TEXT_PATH,
  content: [
    "% Техническое задание. Раздел «Введение»",
    "\\section{Введение}",
    "",
    "\\subsection{Наименование программы}",
    "Полное наименование: «{{ project.name_ru }}».",
    "Краткое наименование: «{{ meta.name_short }}».",
    "",
    "\\subsection{Область применения}",
    "Программа предназначена для {{ project.purpose }}.",
    "",
  ].join("\n"),
  etag: "etag-text",
  readOnly: null,
};

const CONTENT_LINT: PackLint = {
  scope: "version",
  target: CONTENT_VERSION_DIR,
  released: false,
  errors: 0,
  warnings: 0,
  findings: [],
};

const CONTENT_HINTS: PackEditorHints = {
  version: CONTENT_VERSION_DIR,
  meta_fields: [],
  macros: [],
};

/** Модель версии в кэш запросов (то, что `usePackVersionModel` берёт у сервера). */
export const seedContentModel = (
  client: QueryClient,
  model: PackVersionModel = CONTENT_MODEL,
): void => {
  client.setQueryData(
    packStudioKeys.model(GALLERY_WORKSPACE.id, {
      pack: model.pack,
      template: model.template,
      version: model.version,
    }),
    model,
  );
};

/** Текст файла, его проверки и подсказки редактора (для записей с редактором). */
export const seedContentText = (client: QueryClient): void => {
  const ws = GALLERY_WORKSPACE.id;
  seedContentModel(client);
  // Язык интерфейса выбирает редакцию (ru или en): подкладываем обе.
  for (const path of [
    CONTENT_TEXT_PATH,
    CONTENT_TEXT_PATH.replace(".ru.", ".en."),
  ]) {
    client.setQueryData(packStudioKeys.file(ws, path), {
      ...CONTENT_TEXT,
      path,
    });
  }
  client.setQueryData(
    packStudioKeys.lint(ws, CONTENT_VERSION_DIR, "0"),
    CONTENT_LINT,
  );
  client.setQueryData(
    packStudioKeys.hints(ws, CONTENT_VERSION_DIR),
    CONTENT_HINTS,
  );
};

/** Модель версии с `count` документами (для проверки поиска в навигации). */
export const modelWithDocuments = (count: number): PackVersionModel => {
  const extra = Array.from(
    { length: Math.max(0, count - CONTENT_MODEL.documents.length) },
    (_, index) => {
      const id = `extra_document_${String(index + 1)}`;
      const data = {
        name: {
          ru: `Дополнительный документ ${String(index + 1)}`,
          en: `Extra document ${String(index + 1)}`,
        },
        group: "work",
        variants: [{ id: "main", source_file: `${id}/${id}.tex` }],
      };
      return {
        id,
        manifest: modelFile(
          `${CONTENT_VERSION_DIR}/files/${id}/doc.yaml`,
          data,
        ),
        data,
        files: [
          {
            path: `${id}/${id}.tex`,
            bare: `${id}/${id}.tex`,
            lang: "",
            size: 1024,
          },
        ],
        references: [],
      };
    },
  );
  return {
    ...CONTENT_MODEL,
    documents: [...CONTENT_MODEL.documents, ...extra],
  };
};

/** Выпущенная версия 2026.1.2 из галереи каркаса: те же документы, писать нельзя. */
export const RELEASED_MODEL = buildModel("2026.1.2", "version_released");
