import type { z } from "zod";
import type { DocumentResponseSchema } from "@entities/document";
import type {
  MetaFieldDef,
  VersionDetailSchema,
} from "@entities/template-catalog";
import { i18n, metaFieldVisibleForKind, pickLocalized } from "@shared/lib";
import type { AuthorEntry, Project } from "./types";

export type VersionDetail = z.infer<typeof VersionDetailSchema>;
export type ProjectDocument = z.infer<typeof DocumentResponseSchema>;
export type DocumentDefinition = VersionDetail["documents"][number];
export type DocumentVariant = DocumentDefinition["variants"][number];
export type MetaGroupDef = VersionDetail["meta_groups"][number];

// `Object.entries(meta_fields)` tuple — the meta editor renders fields in
// declaration order, so the entries stay an array, never a map.
export type MetaFieldEntry = [key: string, def: MetaFieldDef];

export type MetaFieldGroup = {
  id: string;
  label: string;
  fields: MetaFieldEntry[];
};

export type VariantRow = {
  def: DocumentDefinition;
  doc: ProjectDocument;
  variants: DocumentVariant[];
};

export type VariantGroup = {
  key: string;
  title: string | null;
  rows: VariantRow[];
};

// Meta keys that have a dedicated editor elsewhere and must NOT also appear in
// the generic pack-driven meta editor: `nda` is the Конфиденциальность toggle,
// person-typed fields (supervisor/co_supervisor/norm_ctrl_officer) live in the
// Руководитель section.
const META_KEYS_WITH_OWN_EDITOR = new Set(["nda"]);

// Trailing bucket for fields the pack didn't assign to a declared group.
export const UNGROUPED_META_GROUP_ID = "__ungrouped";

// The «Метаданные» block key of the shared (project-level) values.
export const SHARED_META_BLOCK_KEY = "__shared";

// Pack-driven meta fields (Tier-2): every non-person field except those with
// a dedicated editor. The wizard shows only `required_at: create`; settings
// exposes ALL of them so finalize/optional fields can be edited later too.
// Font slots render in their own «Шрифты документов» section, not here.
export const collectMetaFields = (
  versionDetail: VersionDetail | undefined,
  kind: Project["kind"] | undefined,
): MetaFieldEntry[] =>
  Object.entries(versionDetail?.meta_fields ?? {}).filter(
    ([key, def]) =>
      def.type !== "person" &&
      def.type !== "font" &&
      !META_KEYS_WITH_OWN_EDITOR.has(key) &&
      // Скрываем поля не для этого вида работы (например «Руководства» РП/РО
      // не показываются в исследовательской ВКР).
      metaFieldVisibleForKind(def, kind),
  );

// Pack-declared display groups: fields render under their group's subheading in
// declaration order; stragglers fall into a trailing bucket. Empty groups are
// dropped, so the result doubles as the meta subsection list.
export const groupMetaFields = (
  fields: MetaFieldEntry[],
  metaGroups: readonly MetaGroupDef[],
  ungroupedLabel: string,
): MetaFieldGroup[] =>
  [
    ...metaGroups.map((g) => ({
      id: g.id,
      label: pickLocalized(g.label, i18n.language, g.id),
      fields: fields.filter(([, def]) => def.group === g.id),
    })),
    {
      id: UNGROUPED_META_GROUP_ID,
      label: ungroupedLabel,
      fields: fields.filter(
        ([, def]) => !def.group || !metaGroups.some((g) => g.id === def.group),
      ),
    },
  ].filter((g) => g.fields.length > 0);

// Якорь группы полей в карточке «Метаданные». Оглавление настроек живёт в
// другой ветке дерева (сменная панель верстака), докричаться до карточки может
// только через DOM — поэтому id обязан считаться из одного места обеими
// сторонами, иначе прокрутка молча перестанет находить цель.
// A pack without groups keeps the old flat look (no subheadings).
export const shouldShowMetaGroupHeadings = (
  groups: readonly MetaFieldGroup[],
): boolean => groups.length > 1 || groups[0]?.id !== UNGROUPED_META_GROUP_ID;

/**
 * Страница настроек, на которой пак просит показать группу мета-полей.
 *
 * Не всякое мета-поле — «метаданные»: состав комплекта (какие руководства в
 * него входят) — решение о ДОКУМЕНТАХ, и место ему рядом с форматами шаблонов
 * и ведением комплектов, а не в общей простыне полей титульного листа.
 */
export type MetaGroupSection = "meta" | "documents";

const DEFAULT_META_GROUP_SECTION: MetaGroupSection = "meta";

// Незнакомая секция приходит из пака новее приложения: показываем группу в
// «Метаданных», а не теряем её поля молча.
export const metaGroupSection = (group: MetaGroupDef): MetaGroupSection =>
  group.section === "documents" ? "documents" : DEFAULT_META_GROUP_SECTION;

// Поле без группы (или с неизвестной) живёт в «Метаданных» — там же, где его
// показывает хвостовой bucket groupMetaFields.
const fieldSection = (
  def: MetaFieldDef,
  metaGroups: readonly MetaGroupDef[],
): MetaGroupSection => {
  const group = metaGroups.find((g) => g.id === def.group);
  return group ? metaGroupSection(group) : DEFAULT_META_GROUP_SECTION;
};

/** Поля, оставшиеся за секцией: уведённые паком в другую сюда не попадают. */
export const filterMetaFieldsBySection = (
  fields: readonly MetaFieldEntry[],
  metaGroups: readonly MetaGroupDef[] | undefined,
  section: MetaGroupSection,
): MetaFieldEntry[] =>
  fields.filter(([, def]) => fieldSection(def, metaGroups ?? []) === section);

export type MetaGroupCard = { group: MetaGroupDef; fields: MetaFieldEntry[] };

/**
 * «Одна группа — одна карточка» для секций, куда пак увёл группы: на чужой
 * странице у карточки уже есть свой заголовок (имя группы), и подзаголовки
 * внутри были бы им же продублированы.
 *
 * Группы без полей карточек не получают: в исследовательской ВКР `manuals`
 * скрыт видом работы, и пустая карточка «Состав документов» выглядела бы как
 * поломка.
 */
export const buildMetaGroupCards = (
  fields: readonly MetaFieldEntry[],
  metaGroups: readonly MetaGroupDef[] | undefined,
  section: MetaGroupSection,
): MetaGroupCard[] =>
  (metaGroups ?? [])
    .filter((group) => metaGroupSection(group) === section)
    .map((group) => ({
      group,
      fields: fields.filter(([, def]) => def.group === group.id),
    }))
    .filter((card) => card.fields.length > 0);

export type MetaBlockAuthor = { author: AuthorEntry; index: number };

export type MetaBlock = { key: string; label: string };

// Team: у каждого блока документов свои значения — «Общие документы»
// (project.meta: общее ТЗ + значения по умолчанию) и комплект каждого ведомого
// автора. Solo: единственный блок, переключателя нет.
export const collectManagedTeamAuthors = (
  authors: readonly AuthorEntry[],
  isTeam: boolean,
): MetaBlockAuthor[] =>
  isTeam
    ? authors
        .map((author, index) => ({ author, index }))
        .filter((entry) => entry.author.managed && !!entry.author.slug)
    : [];

export const buildMetaBlocks = (
  managedAuthors: readonly MetaBlockAuthor[],
  sharedLabel: string,
): MetaBlock[] => [
  { key: SHARED_META_BLOCK_KEY, label: sharedLabel },
  ...managedAuthors.map((entry) => {
    // Для вкладки достаточно фамилии; слаг — фолбэк для безымянных.
    const surname = entry.author.name.trim().split(/\s+/)[0] ?? "";
    return {
      key: entry.author.slug ?? "",
      label: surname === "" ? (entry.author.slug ?? "") : surname,
    };
  }),
];

// Every pack definition that declares variants gets a switcher row per project
// instance. Variants restricted by language (IEEE/ISO editions — en-only) are
// hidden in projects of another language; when nothing is left to choose from
// (a lone ГОСТ variant), the row is dropped entirely.
export const collectVariantRows = (
  versionDetail: VersionDetail | undefined,
  projectDocuments: readonly ProjectDocument[] | undefined,
  lang: string | undefined,
): VariantRow[] =>
  (versionDetail?.documents ?? [])
    .filter((def) => def.variants.length > 0)
    .flatMap((def) => {
      const variants = def.variants.filter(
        (v) =>
          v.supported_langs.length === 0 ||
          // `lang` необязателен в ProjectResponseSchema; «ru» — тот же дефолт,
          // что и в остальном приложении (WorkspacePage, DocumentNav).
          v.supported_langs.includes(lang ?? "ru"),
      );
      if (variants.length < 2) return [];
      return (projectDocuments ?? [])
        .filter(
          (doc) => (doc.def_id ?? doc.id.split("--")[0] ?? doc.id) === def.id,
        )
        .map((doc) => ({ def, doc, variants }));
    });

// Team layout mirrors the doc nav: shared docs first (headed only in team),
// then one block per author in project.authors order; unknown owners last.
export const groupVariantRows = (
  rows: readonly VariantRow[],
  authors: readonly AuthorEntry[],
  sharedTitle: string | null,
): VariantGroup[] => {
  const groups: VariantGroup[] = [];
  const shared = rows.filter((r) => r.doc.owner == null);
  if (shared.length > 0) {
    groups.push({ key: "shared", title: sharedTitle, rows: shared });
  }
  const seen = new Set<string>();
  for (const author of authors) {
    if (author.slug == null) continue;
    const owned = rows.filter((r) => r.doc.owner === author.slug);
    if (owned.length === 0) continue;
    seen.add(author.slug);
    groups.push({
      key: `author:${author.slug}`,
      title: owned[0]?.doc.owner_name ?? author.name,
      rows: owned,
    });
  }
  for (const row of rows) {
    const owner = row.doc.owner;
    if (owner == null || seen.has(owner)) continue;
    seen.add(owner);
    groups.push({
      key: `author:${owner}`,
      title: row.doc.owner_name ?? owner,
      rows: rows.filter((r) => r.doc.owner === owner),
    });
  }
  return groups;
};
