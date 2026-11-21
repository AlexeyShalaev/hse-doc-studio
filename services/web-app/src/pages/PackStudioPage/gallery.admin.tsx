import type { QueryClient } from "@tanstack/react-query";
import {
  PackStudioOfficialAdminSchema,
  packStudioKeys,
  type PackServiceAccess,
  type PackStudioAdmin,
  type PackStudioGrant,
} from "@entities/pack-studio";
import {
  CatalogOverviewSchema,
  CatalogSourceSchema,
  packCatalogKeys,
  type CatalogOverview,
  type CatalogSource,
} from "@entities/pack-catalog";
import { PackCatalogAdminPage } from "@features/pack-catalog-admin";
import { PackStudioAdminPage } from "@features/pack-studio-admin";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";

// Галерея админки Студии шаблонов (pack-studio-ux.md, срез S12): страница «Студия
// шаблонов» с чек-листом во всех состояниях и страница «Источники шаблонов».
// Данные лежат в кэше запросов, сервер не нужен.

const NOW = "2026-11-14T09:30:00Z";

const GRANTS: PackStudioGrant[] = [
  {
    id: "g1",
    subject: "user",
    subject_id: "u1",
    name: "Анна Петрова",
    email: "a.petrova@edu.hse.ru",
    org_slug: null,
    org_name: null,
    granted_by: "admin",
    created_at: NOW,
  },
  {
    id: "g2",
    subject: "group",
    subject_id: "g-methodists",
    name: "Методисты",
    email: null,
    org_slug: "fcs",
    org_name: "ФКН",
    granted_by: "admin",
    created_at: NOW,
  },
];

const admin = (patch: Partial<PackStudioAdmin>): PackStudioAdmin => ({
  enabled: true,
  locked: false,
  grants: GRANTS,
  ...patch,
});

const REPOS: PackServiceAccess[] = [
  {
    id: "sa1",
    url: "https://gitlab.hse.ru/fcs/packs.git",
    label: "fcs/packs",
    token_family: "glpat",
    created_by: "admin",
    created_by_name: "Администратор",
    created_at: NOW,
  },
];

const OFFICIAL = PackStudioOfficialAdminSchema.parse({
  repo: {
    url: "https://github.com/AlexeyShalaev/hse-doc-studio",
    web_url: "https://github.com/AlexeyShalaev/hse-doc-studio",
    packs_path: "packs",
    base_branch: "master",
    license: "Apache-2.0",
    license_url:
      "https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/LICENSE",
    contributing_url:
      "https://github.com/AlexeyShalaev/hse-doc-studio/blob/master/CONTRIBUTING.md",
  },
});

const seedAdmin =
  (data: PackStudioAdmin, repos: PackServiceAccess[]) =>
  (client: QueryClient) => {
    client.setQueryData(packStudioKeys.admin(), data);
    client.setQueryData(packStudioKeys.serviceAccess(), repos);
    client.setQueryData(packStudioKeys.officialAdmin(), OFFICIAL);
  };

const adminEntry = (
  id: string,
  title: string,
  data: PackStudioAdmin,
  repos: PackServiceAccess[],
  width: number,
  note?: string,
): GalleryEntry => ({
  id,
  title,
  ...(note ? { note } : {}),
  frame: "page",
  width,
  seed: seedAdmin(data, repos),
  render: () => (
    <div style={{ padding: width < 500 ? "0.75rem" : "1.25rem" }}>
      <PackStudioAdminPage />
    </div>
  ),
});

// Эталоны каталога лежат вне сервиса (contracts/pack-catalog/fixtures).
const overviewFiles = import.meta.glob<unknown>(
  "../../../../../contracts/pack-catalog/fixtures/CatalogOverview/*.json",
  { eager: true, import: "default" },
);
const sourceFiles = import.meta.glob<unknown>(
  "../../../../../contracts/pack-catalog/fixtures/CatalogSource/*.json",
  { eager: true, import: "default" },
);
const fixture = (files: Record<string, unknown>, name: string): unknown => {
  const found = Object.entries(files).find(([path]) =>
    path.endsWith(`/${name}.json`),
  );
  if (!found) throw new Error(`catalog fixture ${name} is missing`);
  return found[1];
};

const WITH_SOURCES: CatalogOverview = CatalogOverviewSchema.parse(
  fixture(overviewFiles, "with_sources"),
);
const EMPTY: CatalogOverview = CatalogOverviewSchema.parse(
  fixture(overviewFiles, "empty"),
);
const source = (name: string): CatalogSource =>
  CatalogSourceSchema.parse(fixture(sourceFiles, name));

/** Все слова состояния источника: подключён, новые версии, не подключался, ошибка, выключен. */
const MANY: CatalogOverview = {
  ...WITH_SOURCES,
  sources: [
    ...WITH_SOURCES.sources.slice(0, 1).map((s) => ({
      ...s,
      pending_versions: 2,
      checked_at: NOW,
    })),
    ...WITH_SOURCES.sources.slice(1),
    source("disabled"),
  ],
};

const catalogEntry = (
  id: string,
  title: string,
  data: CatalogOverview,
  width: number,
  note?: string,
): GalleryEntry => ({
  id,
  title,
  ...(note ? { note } : {}),
  frame: "page",
  width,
  seed: (client) => {
    client.setQueryData(packCatalogKeys.overview(), data);
  },
  render: () => (
    <div style={{ padding: width < 500 ? "0.75rem" : "1.25rem" }}>
      <PackCatalogAdminPage />
    </div>
  ),
});

export const getPackStudioAdminGallery = (): GalleryGroup[] => [
  {
    id: "pack-studio-admin",
    title: "Админка: Студия шаблонов",
    description:
      "Чек-лист «Настройка: N шагов из M», кто может править шаблоны, подключённые репозитории, официальные шаблоны.",
    entries: [
      adminEntry(
        "ps_admin",
        "Настроено: раздел работает",
        admin({}),
        REPOS,
        720,
      ),
      adminEntry(
        "ps_admin_fresh",
        "Раздел выключен, ничего не подключено",
        admin({ enabled: false, grants: [] }),
        [],
        720,
        "Пустые состояния называют причину; у чек-листа кнопки «Выдать доступ» и «Подключить репозиторий».",
      ),
      adminEntry(
        "ps_admin_access",
        "Раздел включён, доступ ещё не выдан",
        admin({ grants: [] }),
        REPOS,
        720,
      ),
      adminEntry(
        "ps_admin_locked",
        "Включение задано окружением",
        admin({ locked: true }),
        REPOS,
        720,
      ),
      adminEntry(
        "ps_admin_phone",
        "Телефон",
        admin({ grants: GRANTS.slice(0, 1) }),
        REPOS,
        390,
      ),
    ],
  },
  {
    id: "pack-catalog-admin",
    title: "Админка: источники шаблонов",
    description:
      "Откуда в мастере проекта берутся шаблоны, кроме встроенных: одно слово о состоянии источника и одна главная кнопка.",
    entries: [
      catalogEntry(
        "pc_sources",
        "Источники во всех состояниях",
        MANY,
        860,
        "Всё подключено, новые версии, не удалось проверить, выключен; кнопка «Проверить» главная там, где нужно действие.",
      ),
      catalogEntry("pc_sources_empty", "Источников нет", EMPTY, 640),
      catalogEntry("pc_sources_phone", "Телефон", MANY, 390),
    ],
  },
];
