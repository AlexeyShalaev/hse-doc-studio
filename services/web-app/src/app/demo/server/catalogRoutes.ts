import { demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";

// Каталог шаблонов для мастера создания проекта в серверном демо: один пак,
// один шаблон, одна версия. Формы совпадают со схемами entities/template-catalog.

const PACK = {
  id: "hse-cs-sse",
  name: {
    ru: "ФКН ВШЭ: программная инженерия",
    en: "HSE CS: software engineering",
  },
  description: {
    ru: "Курсовые, проектные и итоговые работы магистратуры.",
    en: "Coursework, project and final theses of the master programme.",
  },
  maintainer: { name: "HSE Studio", email: "studio@example.org" },
  templates: [
    {
      id: "course-project",
      name: { ru: "Курсовой проект", en: "Course project" },
      short_name: { ru: "КП", en: "CP" },
      icon: "GraduationCap",
      accent_hue: 230,
      default_version: "1.0.0",
    },
  ],
};

const VERSION_ITEM = {
  version: "1.0.0",
  status: "stable",
  released_at: "2026-09-01",
  summary: { ru: "Первая стабильная версия.", en: "First stable version." },
  is_default: true,
};

const VERSION_DETAIL = {
  version: "1.0.0",
  status: "stable",
  supported_staffing: ["solo", "team"],
  author_group_placeholder: "МСПИН261",
  engine_config: { default: "xelatex", allowed: ["xelatex"], passes: 2 },
  documents: [],
  meta_fields: {},
  meta_groups: [],
  signatures: { slots: [] },
  pack_submission: { profiles: [] },
};

export const catalogRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/catalog/packs",
    handler: () => demoJson([PACK]),
  },
  {
    method: "GET",
    pattern: "/catalog/packs/:packId/templates/:templateId/versions",
    handler: () => demoJson([VERSION_ITEM]),
  },
  {
    method: "GET",
    pattern: "/catalog/packs/:packId/templates/:templateId/versions/:version",
    handler: () => demoJson(VERSION_DETAIL),
  },
];
