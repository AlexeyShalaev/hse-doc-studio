import type { QueryClient } from "@tanstack/react-query";
import {
  PackChecksSchema,
  PackSubmissionSchema,
  packChecksKeys,
  packStudioKeys,
  packSubmissionKeys,
} from "@entities/pack-studio";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import {
  GALLERY_REF,
  GALLERY_TREE,
  GALLERY_WORKSPACE,
  SpaceGalleryFrame,
} from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import {
  CONTENT_MODEL,
  CONTENT_TEXT_PATH,
  CONTENT_VERSION_DIR,
  RELEASED_MODEL,
  seedContentModel,
  seedContentText,
} from "./fixtures";
import { slots } from "./slots";

// Записи галереи разделов версии и «Все файлы» (S8d): те же формы `pack-forms`, но каждая на свой
// раздел левой навигации, без полосы вкладок прежней формы.
const WS = GALLERY_WORKSPACE.id;

const submissionFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackSubmission/profiles.json",
  { eager: true, import: "default" },
);
const checksFiles = import.meta.glob<unknown>(
  "../../../../../../contracts/pack-studio/fixtures/PackChecks/version.json",
  { eager: true, import: "default" },
);
const only = (files: Record<string, unknown>): unknown =>
  Object.values(files)[0];

const frameFor = (
  search: string,
  options: { phone?: boolean; version?: string; height?: string } = {},
) => (
  <SpaceGalleryFrame
    tab="content"
    search={search}
    {...(options.version ? { version: options.version } : {})}
    {...(options.height ? { height: options.height } : {})}
  >
    <SpaceScreen slots={slots} phone={options.phone ?? false} />
  </SpaceGalleryFrame>
);

const seedDeadlines = (client: QueryClient) => {
  seedContentModel(client);
  client.setQueryData(
    packSubmissionKeys.of(WS, GALLERY_REF),
    // Манифест версии в модели и в точках сдачи один: иначе форма решит, что отстала, и перечитает.
    {
      ...PackSubmissionSchema.parse(only(submissionFiles)),
      etag: CONTENT_MODEL.manifest.etag,
    },
  );
};

const seedTree = (client: QueryClient) => {
  client.setQueryData(packStudioKeys.tree(WS), {
    ...GALLERY_TREE,
    files: [
      "version.yaml",
      "checks/gost-7.32-2017.yaml",
      "files/common/meta.tex.j2",
      "files/technical_specification/doc.yaml",
      "files/technical_specification/technical_specification.ru.tex",
    ].map((rest) => ({
      path: `${CONTENT_VERSION_DIR}/${rest}`,
      is_dir: false,
      size: 2048,
      read_only: null,
    })),
  });
};

const seedRules = (client: QueryClient) => {
  seedContentModel(client);
  seedTree(client);
  client.setQueryData(
    packChecksKeys.of(WS, GALLERY_REF),
    PackChecksSchema.parse(only(checksFiles)),
  );
};

export const galleryEntries: GalleryEntry[] = [
  {
    id: "sp_content_part_documents",
    title: "Содержимое: «Состав документов»",
    note: "Какие документы входят в версию, порядок и общие части.",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () => frameFor("part=documents", { height: "40rem" }),
  },
  {
    id: "sp_content_part",
    title: "Содержимое: раздел «Данные проекта»",
    note: "Поля проекта и их группы: форма версии на один раздел, без полосы вкладок.",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () => frameFor("part=fields", { height: "40rem" }),
  },
  {
    id: "sp_content_part_forms",
    title: "Содержимое: раздел «Анкеты»",
    note: "Какие вопросы видит студент.",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () => frameFor("part=forms", { height: "40rem" }),
  },
  {
    id: "sp_content_part_deadlines",
    title: "Содержимое: раздел «Сроки и сдача»",
    note: "Точки сдачи, порядок подписания и подписи в точках: заменяет прежнюю форму «Сдача и подписи».",
    frame: "screen",
    width: 1280,
    seed: seedDeadlines,
    render: () => frameFor("part=deadlines", { height: "44rem" }),
  },
  {
    id: "sp_content_part_languages",
    title: "Содержимое: раздел «Языки»",
    note: "Языки версии и файлы документов по языкам.",
    frame: "screen",
    width: 1280,
    seed: seedContentModel,
    render: () => frameFor("part=languages", { height: "40rem" }),
  },
  {
    id: "sp_content_part_rules",
    title: "Содержимое: раздел «Правила проверки»",
    note: "Что включено в версии и файлы с правилами, у которых своя форма.",
    frame: "screen",
    width: 1280,
    seed: seedRules,
    render: () => frameFor("part=rules", { height: "44rem" }),
  },
  {
    id: "sp_content_part_released",
    title: "Содержимое: раздел версии, выпущенная версия",
    note: "Замок, пометка «только смотреть» и «Править копию».",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentModel(client, RELEASED_MODEL);
    },
    render: () =>
      frameFor("part=fields", { version: "2026.1.2", height: "36rem" }),
  },
  {
    id: "sp_content_files",
    title: "Содержимое: «Все файлы»",
    note: "Дерево для опытных, текст с автосохранением, создание пака и шаблона по месту.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentText(client);
      seedTree(client);
    },
    render: () =>
      frameFor(`part=files&file=${encodeURIComponent(CONTENT_TEXT_PATH)}`, {
        height: "40rem",
      }),
  },
  {
    id: "sp_content_files_empty",
    title: "Содержимое: «Все файлы», файл не выбран",
    note: "Подсказка выбрать файл в дереве.",
    frame: "screen",
    width: 1280,
    seed: (client) => {
      seedContentModel(client);
      seedTree(client);
    },
    render: () => frameFor("part=files", { height: "30rem" }),
  },
  {
    id: "sp_content_part_phone",
    title: "Содержимое: раздел версии, телефон",
    note: "Слева ничего: «что редактируем» сворачивается полосой над разделом.",
    frame: "plain",
    width: 390,
    seed: seedContentModel,
    render: () => frameFor("part=languages", { phone: true, height: "40rem" }),
  },
];
