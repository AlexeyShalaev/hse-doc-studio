import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Briefcase,
  Building,
  Check,
  Compass,
  Database,
  File,
  FileText,
  Folder,
  FolderOpen,
  Globe,
  Info,
  Languages,
  Layers,
  Loader2,
  Lock,
  Minus,
  Plus,
  Presentation,
  Tag,
  Trash2,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  usePacks,
  useVersions,
  useVersionDetail,
  type MetaFieldDef,
} from "@entities/template-catalog";
import { useCreateProject, useProjectSuggestions } from "@entities/project";
import { HsePersonLookupButton } from "@entities/hse-person";
import { FolderPickerModal } from "@features/folder-picker";
import {
  emptyAuthor,
  isValidSlug,
  titleSlug,
  translitSlug,
  useCreateWizard,
  type AuthorEntry,
  type SupervisorEntry,
} from "../model/useCreateWizard";
import { Spinner } from "@shared/ui/Spinner";
import { isMetaValueBlank, pickLocalized, seedMetaDefaults } from "@shared/lib";
import { clsx } from "clsx";
import type { PackResponse, VersionListItemResponse } from "@shared/api/types";

type StepDef = {
  id: string;
  icon: LucideIcon;
};

// Meta keys with a dedicated editor elsewhere in the wizard, so they're excluded
// from the generic create-step meta form: `group` duplicates each author's group
// (backfilled in handleCreate); person fields live in the Supervisor step.
const HIDDEN_META_KEYS = new Set(["group"]);

// The plain text/select meta fields the wizard collects at creation time:
// everything marked `required_at: create` that isn't a person field or hidden.
// Shared by StepMeta (rendering) and the wizard (validation) so they never drift.
const getCreateMetaFields = (
  metaFields: Record<string, MetaFieldDef>,
): [string, MetaFieldDef][] =>
  Object.entries(metaFields).filter(
    ([key, def]) =>
      def.required_at === "create" &&
      def.type !== "person" &&
      !HIDDEN_META_KEYS.has(key),
  );

// The primary научный руководитель is required at creation when the pack marks
// the `supervisor` meta field `required_at: create`.
const isSupervisorRequired = (
  metaFields: Record<string, MetaFieldDef>,
): boolean => metaFields.supervisor?.required_at === "create";

// Step titles/subtitles live in the `projectCreate` locale under `steps.<id>`;
// resolved at render time via t() so they follow the interface language.
const STEPS: readonly StepDef[] = [
  { id: "pack", icon: Layers },
  { id: "template", icon: FileText },
  { id: "version", icon: Tag },
  { id: "kind", icon: Compass },
  { id: "folder", icon: Folder },
  { id: "lang", icon: Languages },
  { id: "presentation", icon: Presentation },
  { id: "authors", icon: Users },
  { id: "supervisor", icon: UserCheck },
  { id: "meta", icon: Database },
  { id: "review", icon: Check },
];

const TOTAL_STEPS = STEPS.length;

const Logomark = () => (
  <div
    className="flex items-center justify-center font-mono shrink-0"
    style={{
      width: 22,
      height: 22,
      borderRadius: 5,
      background:
        "linear-gradient(135deg, var(--accent), color-mix(in oklch, var(--accent) 60%, var(--fg-0) 0%))",
      color: "var(--accent-ink)",
      fontWeight: 700,
      fontSize: 10,
      letterSpacing: "-0.02em",
      boxShadow: "0 0 0 1px var(--accent-line)",
    }}
  >
    §
  </div>
);

// ── Step 0: Pack ─────────────────────────────────────────────────────────────
const StepPack = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { data: packs, isLoading } = usePacks();
  const { packId, setField } = useCreateWizard();

  if (isLoading) return <Spinner />;
  const packList = packs ?? [];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 12,
        maxWidth: 720,
      }}
    >
      {packList.map((pack: PackResponse) => {
        const isActive = packId === pack.id;
        return (
          <button
            key={pack.id}
            type="button"
            onClick={() => {
              setField("packId", pack.id);
              setField("templateId", null);
              setField("version", null);
            }}
            className="card hover"
            style={{
              padding: 14,
              textAlign: "left",
              borderColor: isActive ? "var(--accent)" : "var(--border)",
              background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--fg-0)",
                marginBottom: 4,
              }}
            >
              {pickLocalized(pack.name, i18n.language, pack.id)}
            </div>
            <div
              className="dim"
              style={{
                fontSize: 11.5,
                lineHeight: 1.45,
                display: "-webkit-box",
                WebkitLineClamp: 3,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {pickLocalized(pack.description, i18n.language, "")}
            </div>
            <div
              className="mono dimmer"
              style={{ fontSize: 10.5, marginTop: 8 }}
            >
              {t("pack.templatesCount", { count: pack.templates.length })}
            </div>
          </button>
        );
      })}
    </div>
  );
};

// ── Step 1: Template ──────────────────────────────────────────────────────────
const StepTemplate = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { packId, templateId, setField } = useCreateWizard();
  const { data: packs, isLoading } = usePacks();

  const pack = packs?.find((p: PackResponse) => p.id === packId);

  // A pack with a single template has no real choice — auto-pick it so the
  // user doesn't click through a one-option step. With two or more we leave
  // the choice untouched. Only fills in when nothing is selected yet, so going
  // back never clobbers a manual pick.
  useEffect(() => {
    const templates = pack?.templates ?? [];
    if (templateId || templates.length !== 1) return;
    const only = templates[0];
    if (!only) return;
    setField("templateId", only.id);
    setField("version", null);
  }, [pack, templateId, setField]);

  if (isLoading) return <Spinner />;

  if (!pack)
    return (
      <div className="dim" style={{ fontSize: 12 }}>
        {t("template.selectPackFirst")}
      </div>
    );

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 12,
        maxWidth: 720,
      }}
    >
      {pack.templates.map((tpl) => {
        const isActive = templateId === tpl.id;
        return (
          <button
            key={tpl.id}
            type="button"
            onClick={() => {
              setField("templateId", tpl.id);
              setField("version", null);
            }}
            className="card hover"
            style={{
              padding: 14,
              textAlign: "left",
              borderColor: isActive ? "var(--accent)" : "var(--border)",
              background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--fg-0)",
                marginBottom: 4,
              }}
            >
              {pickLocalized(tpl.name, i18n.language, tpl.id)}
            </div>
            <div className="mono dim" style={{ fontSize: 11 }}>
              {pickLocalized(tpl.short_name, i18n.language, "")}
            </div>
          </button>
        );
      })}
    </div>
  );
};

// ── Step 2: Version ───────────────────────────────────────────────────────────
const StepVersion = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { packId, templateId, version, setField } = useCreateWizard();
  const { data: versions, isLoading } = useVersions(
    packId ?? "",
    templateId ?? "",
  );

  // Pre-select the freshest version (latest `released_at`) so the step lands
  // with a sensible default already highlighted — same idea as the "Тип" step
  // arriving on "Прикладная". Only fills in when nothing is chosen yet, so a
  // manual pick (or a value carried back from a later step) is never clobbered.
  useEffect(() => {
    if (version || !versions || versions.length === 0) return;
    const latest = versions.reduce((a, b) =>
      new Date(b.released_at).getTime() > new Date(a.released_at).getTime()
        ? b
        : a,
    );
    setField("version", latest.version);
  }, [versions, version, setField]);

  if (isLoading) return <Spinner />;
  if (!packId || !templateId)
    return (
      <div className="dim" style={{ fontSize: 12 }}>
        {t("version.selectTemplateFirst")}
      </div>
    );

  return (
    <div className="flex flex-col" style={{ gap: 8, maxWidth: 560 }}>
      {(versions ?? []).map((v: VersionListItemResponse) => {
        const isActive = version === v.version;
        return (
          <button
            key={v.version}
            type="button"
            onClick={() => {
              setField("version", v.version);
            }}
            className="card hover flex items-center"
            style={{
              padding: 12,
              gap: 10,
              textAlign: "left",
              borderColor: isActive ? "var(--accent)" : "var(--border)",
              background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                className="mono"
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--fg-0)",
                }}
              >
                {v.version}
              </div>
              <div className="dim" style={{ fontSize: 11.5, marginTop: 2 }}>
                {pickLocalized(v.summary, i18n.language, "")}
              </div>
            </div>
            {v.is_default && (
              <span className="chip accent">{t("version.default")}</span>
            )}
            <span
              className={clsx(
                "sev",
                v.status === "stable" && "ok",
                v.status === "beta" && "warn",
                v.status !== "stable" && v.status !== "beta" && "",
              )}
            >
              {v.status}
            </span>
          </button>
        );
      })}
    </div>
  );
};

// ── Step 3: Kind ──────────────────────────────────────────────────────────────
const StepKind = () => {
  const { t } = useTranslation("projectCreate");
  const { kind, setField } = useCreateWizard();

  const options: {
    value: "research" | "project";
    title: string;
    sub: string;
  }[] = [
    {
      value: "project",
      title: t("kind.projectTitle"),
      sub: t("kind.projectSub"),
    },
    {
      value: "research",
      title: t("kind.researchTitle"),
      sub: t("kind.researchSub"),
    },
  ];

  return (
    <div className="flex" style={{ gap: 12, maxWidth: 560 }}>
      {options.map((o) => {
        const isActive = kind === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => {
              setField("kind", o.value);
            }}
            className="card hover"
            style={{
              flex: 1,
              padding: 16,
              textAlign: "left",
              borderColor: isActive ? "var(--accent)" : "var(--border)",
              background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--fg-0)",
                marginBottom: 4,
              }}
            >
              {o.title}
            </div>
            <div className="dim" style={{ fontSize: 11.5, lineHeight: 1.45 }}>
              {o.sub}
            </div>
          </button>
        );
      })}
    </div>
  );
};

// Join a suggested root folder with the project's slug, preserving the root's
// path style (Windows "\" vs POSIX "/"). With no title yet, just the root.
const joinProjectPath = (root: string, leaf: string): string => {
  const sep = root.includes("\\") ? "\\" : "/";
  const base = root.replace(/[\\/]+$/, "");
  return leaf ? `${base}${sep}${leaf}` : base;
};

// ── Step 4: Folder ────────────────────────────────────────────────────────────
const StepFolder = () => {
  const { t } = useTranslation("projectCreate");
  const { title, folder, setField } = useCreateWizard();
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const { data: suggestions } = useProjectSuggestions();
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Keep the path field scrolled to its end so the meaningful tail (the project
  // folder) stays visible instead of the "C:\Users\…" prefix — but never yank
  // the view while the user is actively editing (caret drives scroll then).
  useEffect(() => {
    const el = folderInputRef.current;
    if (el && document.activeElement !== el) {
      el.scrollLeft = el.scrollWidth;
    }
  }, [folder]);

  const autoFolder = title ? "~/study/" + titleSlug(title) : "";
  const showAutoSuggestion =
    autoFolder !== "" && folder.trim() === "" && autoFolder !== folder;

  // Parent folders existing projects live under, most-used first — one click
  // drops the new project next to the others (root + slug of the title).
  const folderRoots = suggestions?.folder_roots.slice(0, 5) ?? [];

  return (
    <div className="flex flex-col" style={{ gap: 16, maxWidth: 560 }}>
      <div className="field" style={{ gap: 4 }}>
        <label>{t("folder.nameLabel")}</label>
        <input
          type="text"
          className="input"
          placeholder={t("folder.namePlaceholder")}
          value={title}
          onChange={(e) => {
            setField("title", e.target.value);
          }}
          autoFocus
        />
        <div className="hint">{t("folder.nameHint")}</div>
      </div>

      <div className="field" style={{ gap: 4 }}>
        <label>{t("folder.folderLabel")}</label>
        <div className="flex gap-2">
          <input
            ref={folderInputRef}
            type="text"
            className="input mono"
            style={{ flex: 1, minWidth: 0 }}
            placeholder={t("folder.folderPlaceholder")}
            value={folder}
            onChange={(e) => {
              setField("folder", e.target.value);
            }}
          />
          <button
            type="button"
            className="btn"
            onClick={() => {
              setIsPickerOpen(true);
            }}
          >
            <FolderOpen size={13} />
            {t("folder.browse")}
          </button>
        </div>
        <div className="hint">{t("folder.folderHint")}</div>

        {showAutoSuggestion && (
          <button
            type="button"
            onClick={() => {
              setField("folder", autoFolder);
            }}
            className="flex items-center gap-2"
            style={{
              marginTop: 6,
              padding: "8px 10px",
              borderRadius: "var(--r-2)",
              border: "1px dashed var(--border-strong)",
              background: "transparent",
              cursor: "pointer",
              fontSize: 11.5,
              color: "var(--fg-2)",
              textAlign: "left",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-2)";
              e.currentTarget.style.color = "var(--fg-0)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.color = "var(--fg-2)";
            }}
          >
            <Folder size={11} style={{ color: "var(--accent)" }} />
            {t("folder.autoSuggest")}
            <span className="mono" style={{ color: "var(--fg-1)" }}>
              {autoFolder}
            </span>
          </button>
        )}

        {folderRoots.length > 0 && (
          <div style={{ marginTop: showAutoSuggestion ? 10 : 6 }}>
            <div className="hint" style={{ marginBottom: 6 }}>
              {t("folder.recentRoots")}
            </div>
            <div className="flex" style={{ flexWrap: "wrap", gap: 6 }}>
              {folderRoots.map((root) => {
                const target = joinProjectPath(
                  root.path,
                  title ? titleSlug(title) : "",
                );
                const active = folder.trim() !== "" && folder === target;
                const leaf =
                  root.path.split(/[\\/]/).filter(Boolean).pop() ?? root.path;
                return (
                  <button
                    key={root.path}
                    type="button"
                    title={root.path}
                    onClick={() => {
                      setField("folder", target);
                    }}
                    className="flex items-center gap-2"
                    style={{
                      padding: "5px 9px",
                      borderRadius: "var(--r-2)",
                      border: active
                        ? "1px solid var(--accent)"
                        : "1px solid var(--border-strong)",
                      background: active ? "var(--accent-soft)" : "var(--bg-1)",
                      cursor: "pointer",
                      fontSize: 11.5,
                      color: active ? "var(--accent)" : "var(--fg-1)",
                      maxWidth: "100%",
                    }}
                    onMouseEnter={(e) => {
                      if (!active)
                        e.currentTarget.style.background = "var(--bg-2)";
                    }}
                    onMouseLeave={(e) => {
                      if (!active)
                        e.currentTarget.style.background = "var(--bg-1)";
                    }}
                  >
                    <Folder
                      size={11}
                      style={{ color: "var(--accent)", flexShrink: 0 }}
                    />
                    <span
                      className="mono"
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: 220,
                      }}
                    >
                      {leaf}
                    </span>
                    <span
                      style={{
                        flexShrink: 0,
                        fontSize: 10,
                        padding: "0 5px",
                        borderRadius: 999,
                        background: "var(--bg-3)",
                        color: "var(--fg-2)",
                      }}
                    >
                      {root.count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <FolderPickerModal
        isOpen={isPickerOpen}
        onClose={() => {
          setIsPickerOpen(false);
        }}
        onSelect={(path) => {
          // Treat the picked directory as the parent and append the future
          // project folder (transliterated title) — same as the popular-root
          // chips. Manual typing in the field stays untouched.
          setField(
            "folder",
            joinProjectPath(path, title ? titleSlug(title) : ""),
          );
        }}
        initialPath={folder || null}
      />
    </div>
  );
};

// ── Step 5: Lang ──────────────────────────────────────────────────────────────
const StepLang = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { packId, templateId, version, kind, lang, authors, setField } =
    useCreateWizard();
  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  const allDocs = versionDetail?.documents ?? [];
  // Показываем только документы, которые реально войдут в проект — как на шаге
  // «Проверка»: по ВИДУ работы (шаг «Тип»: прикладной — ЕСПД-комплект, иссл. —
  // Аннотация/Отчёт) И по СОСТАВУ (solo/team, выводится из числа авторов).
  // Пустой supported_kinds / supported_staffing = документ есть в любом
  // виде/составе (ВКР/презентация/NDA). Без фильтра по составу общие (shared)
  // документы команды (ОТЗ/ОПМИ) ошибочно показывались бы и в solo-проекте.
  const staffing = authors.length > 1 ? "team" : "solo";
  const docs = allDocs.filter((d) => {
    const kindOk =
      !kind || !d.supported_kinds?.length || d.supported_kinds.includes(kind);
    const staffingOk =
      !d.supported_staffing?.length || d.supported_staffing.includes(staffing);
    return kindOk && staffingOk;
  });
  // Empty supported_langs[] = template doesn't declare per-doc coverage →
  // treat as "available everywhere" so old templates keep working.
  const supports = (d: (typeof docs)[number], l: "ru" | "en"): boolean =>
    !d.supported_langs || d.supported_langs.length === 0
      ? true
      : d.supported_langs.includes(l);
  const enCount = docs.filter((d) => supports(d, "en")).length;
  const ruCount = docs.filter((d) => supports(d, "ru")).length;

  const hintFor = (l: "ru" | "en") => {
    if (docs.length === 0) return l === "ru" ? "ru-RU" : "en-US";
    const code = l === "ru" ? "ru-RU" : "en-US";
    const count = l === "ru" ? ruCount : enCount;
    // Исследовательский вид — не ЕСПД-комплект, поэтому «полный комплект».
    if (count === docs.length)
      return t(kind === "research" ? "lang.fullSet" : "lang.fullEspd", {
        code,
      });
    if (count === 0) return t("lang.noTranslations", { code });
    return t("lang.partial", { code, count, total: docs.length });
  };

  return (
    <div className="flex flex-col" style={{ gap: 16, maxWidth: 640 }}>
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
        {t("lang.intro")}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
        }}
      >
        {(["ru", "en"] as const).map((l) => {
          const isActive = lang === l;
          return (
            <button
              key={l}
              type="button"
              onClick={() => {
                setField("lang", l);
              }}
              className="card hover"
              style={{
                padding: 14,
                textAlign: "left",
                borderColor: isActive ? "var(--accent)" : "var(--border)",
                background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
              }}
            >
              <div
                className="flex items-center gap-2"
                style={{ marginBottom: 4 }}
              >
                <Languages
                  size={14}
                  style={{
                    color: isActive ? "var(--accent)" : "var(--fg-2)",
                  }}
                />
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--fg-0)",
                  }}
                >
                  {l === "ru" ? t("lang.russian") : t("lang.english")}
                </span>
              </div>
              <div className="mono dim" style={{ fontSize: 11 }}>
                {hintFor(l)}
              </div>
            </button>
          );
        })}
      </div>

      {docs.length > 0 && (
        <div
          className="card"
          style={{ padding: 12, background: "var(--bg-2)" }}
        >
          <div className="flex items-center gap-2" style={{ marginBottom: 10 }}>
            <Info size={13} style={{ color: "var(--c-info)" }} />
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>
              {t("lang.tableTitle")}
            </span>
          </div>
          <div className="flex flex-col" style={{ gap: 4 }}>
            {docs.map((d) => (
              <div
                key={d.id}
                className="flex items-center"
                style={{ gap: 10, fontSize: 12 }}
              >
                <span
                  className="chip mono"
                  style={{
                    fontSize: 10,
                    minWidth: 48,
                    justifyContent: "center",
                  }}
                >
                  {pickLocalized(d.code, i18n.language, d.id.toUpperCase())}
                </span>
                <span
                  style={{
                    flex: 1,
                    color: "var(--fg-1)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pickLocalized(d.name, i18n.language, d.id)}
                </span>
                <LangCell available={supports(d, "ru")} />
                <LangCell available={supports(d, "en")} />
              </div>
            ))}
          </div>
          <div
            className="flex items-center"
            style={{
              gap: 10,
              marginTop: 8,
              paddingTop: 8,
              borderTop: "1px solid var(--border-soft)",
              fontSize: 10,
            }}
          >
            <span style={{ flex: 1 }} />
            <span
              className="mono dim"
              style={{ width: 16, textAlign: "center" }}
            >
              RU
            </span>
            <span
              className="mono dim"
              style={{ width: 16, textAlign: "center" }}
            >
              EN
            </span>
          </div>
        </div>
      )}
      {/* Документ без поддержки выбранного языка (например Расписка NDA —
          всегда на русском) всё равно входит в комплект, просто на своём
          языке. Показываем пояснение, когда такие документы есть. */}
      {docs.length > 0 && (lang === "ru" ? ruCount : enCount) < docs.length && (
        <div className="dim" style={{ fontSize: 11, lineHeight: 1.5 }}>
          {t("lang.inclusionNote")}
        </div>
      )}
    </div>
  );
};

const LangCell = ({ available }: { available: boolean }) =>
  available ? (
    <Check
      size={13}
      style={{ color: "var(--c-ok)", width: 16, flexShrink: 0 }}
    />
  ) : (
    <Minus
      size={13}
      style={{ color: "var(--fg-3)", width: 16, flexShrink: 0 }}
    />
  );

// ── Step 6: Authors ───────────────────────────────────────────────────────────
// ── Step: Presentation format ─────────────────────────────────────────────
// Explicit choice of the presentation document's format. Options come from the
// backend (the `presentation` doc's `variants` for the chosen template/version),
// so the pack owns the list per language — the user picks here instead of
// discovering the alternatives later in project settings.
const presIconFor = (outputFile: string | null | undefined): LucideIcon => {
  const ext = (outputFile ?? "").split(".").pop()?.toLowerCase();
  if (ext === "pptx") return Presentation;
  if (ext === "html" || ext === "htm") return Globe;
  if (ext === "pdf" || ext === "tex") return FileText;
  return File;
};

const StepPresentation = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { packId, templateId, version, presVariant, setField } =
    useCreateWizard();
  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  const presDoc = (versionDetail?.documents ?? []).find(
    (d) => d.id === "presentation",
  );
  const variants = presDoc?.variants ?? [];
  // Default highlight mirrors the backend (_resolve_variant → variants[0]) so
  // the active card matches what's created if the user just clicks «Далее».
  const selected = presVariant ?? variants[0]?.id ?? null;

  if (!versionDetail) return <Spinner />;
  if (variants.length === 0) {
    return (
      <div className="dim" style={{ fontSize: 12.5, maxWidth: 560 }}>
        {t("presentation.none")}
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: 16, maxWidth: 640 }}>
      <div className="dim" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
        {t("presentation.intro")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {variants.map((v) => {
          const isActive = selected === v.id;
          const VIcon = presIconFor(v.output_file);
          const ext = (v.output_file ?? "").split(".").pop()?.toLowerCase();
          return (
            <button
              key={v.id}
              type="button"
              onClick={() => {
                setField("presVariant", v.id);
              }}
              className="card hover"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: 14,
                textAlign: "left",
                borderColor: isActive ? "var(--accent)" : "var(--border)",
                background: isActive ? "var(--accent-soft)" : "var(--bg-1)",
              }}
            >
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 8,
                  background: isActive ? "var(--accent-soft)" : "var(--bg-0)",
                  color: isActive ? "var(--accent)" : "var(--fg-2)",
                }}
              >
                <VIcon size={17} />
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--fg-0)",
                  }}
                >
                  {pickLocalized(v.label, i18n.language, v.id)}
                </div>
                <div
                  className="dim"
                  style={{ fontSize: 11, lineHeight: 1.4, marginTop: 2 }}
                >
                  {t(`presentation.desc.${v.id}`, {
                    defaultValue: t("presentation.descFallback"),
                  })}
                </div>
              </div>
              {ext && (
                <span className="mono dim shrink-0" style={{ fontSize: 10 }}>
                  .{ext}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};

const StepAuthors = () => {
  const { t } = useTranslation("projectCreate");
  const { packId, templateId, version, authors, sharedEnabled, setField } =
    useCreateWizard();
  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  const isTeam = authors.length > 1;
  const supportsTeam = (versionDetail?.supported_staffing ?? ["solo"]).includes(
    "team",
  );

  const { data: suggestions } = useProjectSuggestions();
  const [openNameIdx, setOpenNameIdx] = useState<number | null>(null);

  const handlePatchAuthor = (idx: number, patch: Partial<AuthorEntry>) => {
    setField(
      "authors",
      authors.map((a, i) => (i === idx ? { ...a, ...patch } : a)),
    );
  };

  // The slug follows the transliterated surname while the user hasn't edited
  // it manually — i.e. while it's still empty or equal to the auto value of
  // the previous name. A hand-edited slug is never clobbered.
  const handleNameChange = (idx: number, name: string) => {
    const current = authors[idx];
    if (!current) return;
    const followsAuto =
      current.slug === "" || current.slug === translitSlug(current.name);
    handlePatchAuthor(idx, {
      name,
      ...(followsAuto ? { slug: translitSlug(name) } : {}),
    });
  };

  // Autocomplete the ФИО from authors seen in existing projects — like a
  // search over people. Substring match, exact match dropped (nothing left to
  // complete), capped so the dropdown stays small.
  const nameOptions = (query: string) => {
    const q = query.trim().toLowerCase();
    const all = suggestions?.authors ?? [];
    return (q ? all.filter((a) => a.name.toLowerCase().includes(q)) : all)
      .filter((a) => a.name.toLowerCase() !== q)
      .slice(0, 6);
  };

  // Picking a suggestion fills the name (slug follows the surname while it's
  // still auto) and back-fills the group when the row's group is still empty.
  const handlePickAuthor = (
    idx: number,
    picked: { name: string; group: string },
  ) => {
    const current = authors[idx];
    const followsAuto =
      !current ||
      current.slug === "" ||
      current.slug === translitSlug(current.name);
    handlePatchAuthor(idx, {
      name: picked.name,
      ...(followsAuto ? { slug: translitSlug(picked.name) } : {}),
      ...(picked.group && (current?.group ?? "").trim() === ""
        ? { group: picked.group }
        : {}),
    });
    setOpenNameIdx(null);
  };

  const handleAddAuthor = () => {
    setField("authors", [...authors, emptyAuthor()]);
  };

  const handleRemoveAuthor = (idx: number) => {
    setField(
      "authors",
      authors.filter((_, i) => i !== idx),
    );
  };

  return (
    <div className="flex flex-col" style={{ gap: 10, maxWidth: 560 }}>
      {isTeam && versionDetail !== undefined && !supportsTeam && (
        <div
          className="card flex items-start"
          style={{
            gap: 8,
            padding: 12,
            borderColor: "var(--c-err)",
            background: "var(--c-err-soft)",
            color: "var(--c-err)",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 2 }} />
          <span>{t("authors.teamNotSupported")}</span>
        </div>
      )}

      {isTeam && (
        <div
          className="card flex items-start"
          style={{
            gap: 8,
            padding: 12,
            background: "var(--bg-2)",
            color: "var(--fg-1)",
            fontSize: 11.5,
            lineHeight: 1.5,
          }}
        >
          <Info
            size={13}
            style={{ color: "var(--c-info)", flexShrink: 0, marginTop: 2 }}
          />
          <span>{t("authors.teamIntro")}</span>
        </div>
      )}

      {authors.map((author, idx) => {
        const slugError = !isValidSlug(author.slug)
          ? t("authors.slugInvalid")
          : authors.some((other, i) => i !== idx && other.slug === author.slug)
            ? t("authors.slugDuplicate")
            : null;
        const rowNameOptions =
          openNameIdx === idx ? nameOptions(author.name) : [];
        return (
          <div
            key={idx}
            className="card"
            style={{ padding: 12, position: "relative" }}
          >
            <div
              className="flex items-center justify-between"
              style={{ marginBottom: 8 }}
            >
              <span className="label-up dim">
                {t("authors.author", { index: idx + 1 })}
              </span>
              {authors.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    handleRemoveAuthor(idx);
                  }}
                  className="icon-btn sm"
                  title={t("authors.removeTitle")}
                  aria-label={t("authors.removeAria")}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
            <div className="flex" style={{ gap: 8 }}>
              <div className="field" style={{ flex: 2, minWidth: 0, gap: 4 }}>
                <label>{t("authors.nameLabel")}</label>
                <div style={{ position: "relative" }}>
                  <input
                    type="text"
                    className="input"
                    style={{ width: "100%" }}
                    placeholder={t("authors.namePlaceholder")}
                    value={author.name}
                    autoComplete="off"
                    onChange={(e) => {
                      handleNameChange(idx, e.target.value);
                      setOpenNameIdx(idx);
                    }}
                    onFocus={() => {
                      setOpenNameIdx(idx);
                    }}
                    onBlur={() => {
                      // Delay so a suggestion's click registers before we close.
                      window.setTimeout(() => {
                        setOpenNameIdx((cur) => (cur === idx ? null : cur));
                      }, 120);
                    }}
                    autoFocus={idx === authors.length - 1 && author.name === ""}
                  />
                  {rowNameOptions.length > 0 && (
                    <div
                      className="card"
                      style={{
                        position: "absolute",
                        top: "calc(100% + 4px)",
                        left: 0,
                        right: 0,
                        zIndex: 30,
                        padding: 4,
                        maxHeight: 208,
                        overflowY: "auto",
                        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.18)",
                      }}
                    >
                      {rowNameOptions.map((s) => (
                        <button
                          key={`${s.name}__${s.group}`}
                          type="button"
                          onMouseDown={(e) => {
                            e.preventDefault();
                          }}
                          onClick={() => {
                            handlePickAuthor(idx, s);
                          }}
                          className="flex items-center justify-between"
                          style={{
                            width: "100%",
                            textAlign: "left",
                            gap: 8,
                            padding: "6px 8px",
                            borderRadius: "var(--r-2)",
                            border: "none",
                            background: "transparent",
                            cursor: "pointer",
                            fontSize: 12.5,
                            color: "var(--fg-0)",
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = "var(--bg-2)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = "transparent";
                          }}
                        >
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {s.name}
                          </span>
                          {s.group && (
                            <span
                              className="mono"
                              style={{
                                flexShrink: 0,
                                fontSize: 10.5,
                                color: "var(--fg-2)",
                              }}
                            >
                              {s.group}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="field" style={{ flex: 1, minWidth: 120, gap: 4 }}>
                <label>{t("authors.groupLabel")}</label>
                <input
                  type="text"
                  className="input mono"
                  placeholder={t("authors.groupPlaceholder")}
                  value={author.group}
                  onChange={(e) => {
                    handlePatchAuthor(idx, { group: e.target.value });
                  }}
                />
              </div>
            </div>

            {isTeam && (
              <>
                <div className="field" style={{ gap: 4, marginTop: 10 }}>
                  <label>
                    {t("authors.topicLabel")}
                    {author.managed && (
                      <span style={{ color: "var(--c-err)", marginLeft: 4 }}>
                        *
                      </span>
                    )}
                  </label>
                  <input
                    type="text"
                    className="input"
                    placeholder={t("authors.topicPlaceholder")}
                    value={author.topic}
                    onChange={(e) => {
                      handlePatchAuthor(idx, { topic: e.target.value });
                    }}
                  />
                  {author.managed && author.topic.trim() === "" && (
                    <div className="hint" style={{ color: "var(--c-err)" }}>
                      {t("authors.topicRequired")}
                    </div>
                  )}
                </div>
                <div
                  className="flex"
                  style={{ gap: 12, marginTop: 10, alignItems: "flex-start" }}
                >
                  <div
                    className="field"
                    style={{ flex: 1, minWidth: 0, gap: 4 }}
                  >
                    <label>{t("authors.slugLabel")}</label>
                    <input
                      type="text"
                      className="input mono"
                      placeholder="ivanov"
                      value={author.slug}
                      onChange={(e) => {
                        handlePatchAuthor(idx, { slug: e.target.value });
                      }}
                    />
                    {slugError ? (
                      <div className="hint" style={{ color: "var(--c-err)" }}>
                        {slugError}
                      </div>
                    ) : (
                      <div className="hint">{t("authors.slugHint")}</div>
                    )}
                  </div>
                  <label
                    className="flex items-center cursor-pointer"
                    style={{ gap: 8, paddingTop: 24, flexShrink: 0 }}
                  >
                    <input
                      type="checkbox"
                      checked={author.managed}
                      onChange={(e) => {
                        handlePatchAuthor(idx, { managed: e.target.checked });
                      }}
                      style={{ accentColor: "var(--accent)" }}
                    />
                    <span style={{ fontSize: 12 }}>
                      {t("authors.managedLabel")}
                    </span>
                  </label>
                </div>
                {!author.managed && (
                  <div className="hint" style={{ marginTop: 4 }}>
                    {t("authors.notManagedHint")}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}

      {isTeam && !authors.some((a) => a.managed) && (
        <div className="hint" style={{ color: "var(--c-err)" }}>
          {t("authors.needManaged")}
        </div>
      )}

      <button
        type="button"
        onClick={handleAddAuthor}
        className="flex items-center justify-center"
        style={{
          padding: "12px 14px",
          gap: 6,
          fontSize: 12,
          borderRadius: "var(--r-3)",
          border: "1px dashed var(--border-strong)",
          background: "transparent",
          color: "var(--fg-2)",
          cursor: "pointer",
          transition: "background 0.12s, color 0.12s, border-color 0.12s",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--bg-2)";
          e.currentTarget.style.color = "var(--fg-0)";
          e.currentTarget.style.borderColor = "var(--accent-line)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.color = "var(--fg-2)";
          e.currentTarget.style.borderColor = "var(--border-strong)";
        }}
      >
        <Plus size={13} />
        {t("authors.addMore")}
      </button>

      {isTeam && (
        <div className="card" style={{ padding: 14 }}>
          <div className="flex items-start justify-between" style={{ gap: 12 }}>
            <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
              <div className="flex items-center gap-2">
                <FolderOpen
                  size={13}
                  style={{
                    color: sharedEnabled ? "var(--accent)" : "var(--fg-3)",
                    flexShrink: 0,
                  }}
                />
                <strong style={{ fontSize: 12.5 }}>
                  {t("authors.sharedTitle")}
                </strong>
              </div>
              <p
                className="dim"
                style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}
              >
                {t("authors.sharedDescription")}
              </p>
            </div>
            <button
              type="button"
              className={clsx("toggle", sharedEnabled && "on")}
              onClick={() => {
                setField("sharedEnabled", !sharedEnabled);
              }}
              aria-pressed={sharedEnabled}
              aria-label={t("authors.sharedAria")}
              style={{ flexShrink: 0 }}
            />
          </div>
        </div>
      )}

      <div className="hint" style={{ marginTop: 4 }}>
        {t("authors.hint")}
      </div>
    </div>
  );
};

// ── Step 7: Supervisor ────────────────────────────────────────────────────────
type SupervisorCardProps = {
  title: string;
  value: SupervisorEntry;
  onChange: (patch: Partial<SupervisorEntry>) => void;
  primary?: boolean;
  required?: boolean;
};

const SupervisorCard = ({
  title,
  value,
  onChange,
  primary,
  required,
}: SupervisorCardProps) => {
  const { t } = useTranslation("projectCreate");
  return (
    <div className="card" style={{ padding: 14 }}>
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: 10, gap: 8, flexWrap: "wrap" }}
      >
        <div className="flex items-center gap-2">
          {value.role === "university" ? (
            <Building
              size={13}
              style={{ color: "var(--accent)", flexShrink: 0 }}
            />
          ) : (
            <Briefcase
              size={13}
              style={{ color: "var(--c-warn)", flexShrink: 0 }}
            />
          )}
          <strong style={{ fontSize: 12.5 }}>{title}</strong>
          {primary &&
            (required ? (
              <span style={{ color: "var(--c-err)", fontSize: 10.5 }}>
                {t("supervisor.required")}
              </span>
            ) : (
              <span className="dim" style={{ fontSize: 10.5 }}>
                {t("supervisor.optional")}
              </span>
            ))}
        </div>
        <div className="seg">
          <button
            type="button"
            className={clsx(value.role === "university" && "active")}
            onClick={() => {
              onChange({ role: "university" });
            }}
          >
            <Building size={10} />
            {t("supervisor.fromUniversity")}
          </button>
          <button
            type="button"
            className={clsx(value.role === "company" && "active")}
            onClick={() => {
              onChange({ role: "company" });
            }}
          >
            <Briefcase size={10} />
            {t("supervisor.fromCompany")}
          </button>
        </div>
      </div>
      <div className="flex justify-end" style={{ marginBottom: 8 }}>
        <HsePersonLookupButton
          initialQuery={value.name}
          onSelect={(fields) => {
            onChange({
              role: "university",
              name: fields.name,
              title: fields.title,
              degree: fields.degree,
            });
          }}
        />
      </div>
      <div className="flex flex-col" style={{ gap: 10 }}>
        <div className="field" style={{ gap: 4 }}>
          <label>{t("supervisor.nameLabel")}</label>
          <input
            type="text"
            className="input"
            placeholder={
              value.role === "university"
                ? t("supervisor.namePlaceholderUniversity")
                : t("supervisor.namePlaceholderCompany")
            }
            value={value.name}
            onChange={(e) => {
              onChange({ name: e.target.value });
            }}
          />
        </div>
        <div className="field" style={{ gap: 4 }}>
          <label>
            {value.role === "university"
              ? t("supervisor.titleLabelUniversity")
              : t("supervisor.titleLabelCompany")}
          </label>
          <input
            type="text"
            className="input"
            placeholder={
              value.role === "university"
                ? t("supervisor.titlePlaceholderUniversity")
                : t("supervisor.titlePlaceholderCompany")
            }
            value={value.title}
            onChange={(e) => {
              onChange({ title: e.target.value });
            }}
          />
        </div>
      </div>
    </div>
  );
};

const StepSupervisor = () => {
  const { t } = useTranslation("projectCreate");
  const {
    packId,
    templateId,
    version,
    supervisor,
    coSupervisorEnabled,
    coSupervisor,
    setField,
  } = useCreateWizard();
  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );
  const required = isSupervisorRequired(versionDetail?.meta_fields ?? {});

  return (
    <div className="flex flex-col" style={{ gap: 14, maxWidth: 560 }}>
      <SupervisorCard
        title={t("supervisor.primaryTitle")}
        primary
        required={required}
        value={supervisor}
        onChange={(patch) => {
          setField("supervisor", { ...supervisor, ...patch });
        }}
      />

      <div className="flex items-center" style={{ gap: 10 }}>
        <span
          style={{
            flex: 1,
            height: 1,
            background: "var(--border)",
          }}
        />
        <button
          type="button"
          className="btn xs ghost"
          onClick={() => {
            setField("coSupervisorEnabled", !coSupervisorEnabled);
          }}
        >
          {coSupervisorEnabled ? (
            <>
              <Minus size={11} />
              {t("supervisor.removeCo")}
            </>
          ) : (
            <>
              <Plus size={11} />
              {t("supervisor.addCo")}
            </>
          )}
        </button>
        <span
          style={{
            flex: 1,
            height: 1,
            background: "var(--border)",
          }}
        />
      </div>

      {coSupervisorEnabled && (
        <div className="fade-up">
          <SupervisorCard
            title={t("supervisor.coTitle")}
            value={coSupervisor}
            onChange={(patch) => {
              setField("coSupervisor", { ...coSupervisor, ...patch });
            }}
          />
        </div>
      )}

      <div className="hint">
        {required ? t("supervisor.hintRequired") : t("supervisor.hint")}
      </div>
    </div>
  );
};

// ── Step 8: Meta ──────────────────────────────────────────────────────────────
const StepMeta = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const { packId, templateId, version, meta, nda, setField } =
    useCreateWizard();
  const { data: versionDetail, isLoading } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  // `person` fields (supervisor…) have their own step; `group` is backfilled
  // from the first author — both are excluded by getCreateMetaFields. Values are
  // pre-seeded with the pack's default / computed `auto` (see the wizard's seed
  // effect), so degree type, programme and defense year arrive already filled.
  const createFields = getCreateMetaFields(versionDetail?.meta_fields ?? {});

  return (
    <div className="flex flex-col" style={{ gap: 14, maxWidth: 560 }}>
      {isLoading ? (
        <Spinner />
      ) : createFields.length === 0 ? (
        <div
          className="card flex items-center"
          style={{
            padding: 12,
            gap: 8,
            background: "var(--bg-2)",
            color: "var(--fg-2)",
            fontSize: 12,
          }}
        >
          <Check size={13} style={{ color: "var(--c-ok)", flexShrink: 0 }} />
          {t("meta.noRequired")}
        </div>
      ) : (
        <div className="flex flex-col" style={{ gap: 12 }}>
          {createFields.map(([key, def]) => {
            const value = (meta[key] as string | undefined) ?? "";
            const help = pickLocalized(
              def.help ?? undefined,
              i18n.language,
              "",
            );
            return (
              <div key={key} className="field" style={{ gap: 4 }}>
                <label>
                  {pickLocalized(def.label, i18n.language, key)}
                  <span style={{ color: "var(--c-err)", marginLeft: 4 }}>
                    *
                  </span>
                </label>
                {def.type === "select" && (def.options ?? []).length > 0 ? (
                  <select
                    className="input"
                    value={value}
                    onChange={(e) => {
                      setField("meta", { ...meta, [key]: e.target.value });
                    }}
                  >
                    <option value="">—</option>
                    {(def.options ?? []).map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="input"
                    placeholder={def.placeholder ?? ""}
                    value={value}
                    onChange={(e) => {
                      setField("meta", { ...meta, [key]: e.target.value });
                    }}
                  />
                )}
                {isMetaValueBlank(value) ? (
                  <div className="hint" style={{ color: "var(--c-err)" }}>
                    {t("meta.requiredField")}
                  </div>
                ) : help ? (
                  <div className="hint">{help}</div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <div className="card" style={{ padding: 14 }}>
        <div className="flex items-start justify-between" style={{ gap: 12 }}>
          <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
            <div className="flex items-center gap-2">
              <Lock
                size={13}
                style={{
                  color: nda ? "var(--c-warn)" : "var(--fg-3)",
                  flexShrink: 0,
                }}
              />
              <strong style={{ fontSize: 12.5 }}>{t("meta.ndaTitle")}</strong>
            </div>
            <p
              className="dim"
              style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}
            >
              {t("meta.ndaDescription")}
            </p>
          </div>
          <button
            type="button"
            className={clsx("toggle", nda && "on")}
            onClick={() => {
              setField("nda", !nda);
            }}
            aria-pressed={nda}
            aria-label={t("meta.ndaAria")}
            style={{ flexShrink: 0 }}
          />
        </div>
        {nda && (
          <div
            className="flex items-center fade-up"
            style={{
              gap: 8,
              marginTop: 10,
              padding: "8px 10px",
              background: "var(--c-warn-soft)",
              color: "var(--c-warn)",
              borderRadius: "var(--r-2)",
              fontSize: 11.5,
            }}
          >
            <AlertTriangle size={12} style={{ flexShrink: 0 }} />
            <span>{t("meta.ndaWarning")}</span>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Step 9: Review ────────────────────────────────────────────────────────────
type FieldRowProps = {
  icon: LucideIcon;
  label: string;
  children: React.ReactNode;
};

const FieldRow = ({ icon: Icon, label, children }: FieldRowProps) => (
  <div
    className="flex items-center"
    style={{
      gap: 12,
      padding: "8px 0",
      borderBottom: "1px dashed var(--border-soft)",
      fontSize: 12.5,
      minWidth: 0,
    }}
  >
    <Icon size={12} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
    <span
      className="mono dim"
      style={{
        width: 100,
        flexShrink: 0,
        fontSize: 9.5,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
      }}
    >
      {label}
    </span>
    <div style={{ flex: 1, minWidth: 0, color: "var(--fg-0)" }}>{children}</div>
  </div>
);

const SupervisorRow = ({
  label,
  value,
}: {
  label: string;
  value: SupervisorEntry;
}) =>
  value.name.trim() ? (
    <FieldRow
      icon={value.role === "company" ? Briefcase : Building}
      label={label}
    >
      <span>
        {value.name}
        {value.title && (
          <span className="dim" style={{ marginLeft: 6 }}>
            · {value.title}
          </span>
        )}
      </span>
    </FieldRow>
  ) : null;

const StepReview = () => {
  const { t, i18n } = useTranslation("projectCreate");
  const {
    packId,
    templateId,
    version,
    kind,
    title,
    folder,
    lang,
    presVariant,
    authors,
    sharedEnabled,
    supervisor,
    coSupervisorEnabled,
    coSupervisor,
    nda,
  } = useCreateWizard();
  const { data: packs } = usePacks();
  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  const pack = packs?.find((p: PackResponse) => p.id === packId);
  const tpl = pack?.templates.find((t) => t.id === templateId);
  const filledAuthors = authors.filter((a) => a.name.trim() !== "");
  const isTeam = authors.length > 1;
  const staffing = isTeam ? "team" : "solo";
  // Превью комплекта = только то, что реально войдёт в проект: по виду работы
  // (прикладной/исследовательский) и режиму состава (solo/team). На этом шаге
  // известно и то, и другое, поэтому список точный.
  const documents = (versionDetail?.documents ?? []).filter((d) => {
    const kindOk =
      !kind || !d.supported_kinds?.length || d.supported_kinds.includes(kind);
    const staffingOk =
      !d.supported_staffing?.length || d.supported_staffing.includes(staffing);
    return kindOk && staffingOk;
  });
  // Chosen presentation format for the summary (mirrors the «Презентация» step:
  // explicit pick, else the template's first variant).
  const presVariants =
    documents.find((d) => d.id === "presentation")?.variants ?? [];
  const chosenPres =
    presVariants.find((v) => v.id === presVariant) ?? presVariants[0];
  const showCoSupervisor =
    coSupervisorEnabled && coSupervisor.name.trim() !== "";

  return (
    <div className="flex flex-col" style={{ gap: 12, maxWidth: 560 }}>
      {/* Summary card */}
      <div className="card" style={{ padding: 16 }}>
        <div
          className="flex items-start justify-between"
          style={{ gap: 12, marginBottom: 14 }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <h3
              style={{
                margin: "0 0 4px",
                fontSize: 15,
                fontWeight: 600,
                color: "var(--fg-0)",
                letterSpacing: "-0.01em",
              }}
            >
              {title.trim() || (
                <span className="dim">{t("review.untitled")}</span>
              )}
            </h3>
            <div
              className="flex items-center"
              style={{ gap: 6, flexWrap: "wrap" }}
            >
              <span className="chip accent">
                {pickLocalized(tpl?.name, i18n.language, templateId ?? "—")}
              </span>
              <span className="chip mono">{lang.toUpperCase()}</span>
              <span className="chip">
                {kind === "research"
                  ? t("review.research")
                  : t("review.project")}
              </span>
              {nda && (
                <span className="sev warn">
                  <Lock size={9} />
                  NDA
                </span>
              )}
            </div>
          </div>
        </div>

        <FieldRow icon={Folder} label={t("review.folderLabel")}>
          <span
            className="mono"
            style={{
              fontSize: 11.5,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              display: "block",
            }}
            title={folder}
          >
            {folder || "—"}
          </span>
        </FieldRow>

        <FieldRow icon={Layers} label={t("review.packLabel")}>
          {pickLocalized(pack?.name, i18n.language, packId ?? "—")}
        </FieldRow>

        <FieldRow icon={Tag} label={t("review.versionLabel")}>
          <span className="mono">{version ?? "—"}</span>
        </FieldRow>

        {chosenPres && (
          <FieldRow icon={Presentation} label={t("review.presentationLabel")}>
            {pickLocalized(chosenPres.label, i18n.language, chosenPres.id)}
          </FieldRow>
        )}

        <FieldRow icon={Users} label={t("review.authorsLabel")}>
          {filledAuthors.length === 0 ? (
            <span className="dim">{t("review.noAuthors")}</span>
          ) : (
            <div className="flex flex-col" style={{ gap: isTeam ? 6 : 2 }}>
              {filledAuthors.map((a, i) => (
                <div key={i}>
                  <div
                    className="flex items-center"
                    style={{ gap: 6, flexWrap: "wrap" }}
                  >
                    <span>{a.name}</span>
                    {a.group && <span className="mono dim">({a.group})</span>}
                    {isTeam && a.slug && (
                      <span className="chip mono" style={{ fontSize: 10 }}>
                        {a.slug}/
                      </span>
                    )}
                    {isTeam && (
                      <span
                        className={clsx("sev", a.managed && "ok")}
                        style={{ fontSize: 10 }}
                      >
                        {a.managed
                          ? t("review.managedBadge")
                          : t("review.notManagedBadge")}
                      </span>
                    )}
                  </div>
                  {isTeam && a.topic.trim() !== "" && (
                    <div
                      className="dim"
                      style={{ fontSize: 11.5, marginTop: 1 }}
                    >
                      {a.topic}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </FieldRow>

        {isTeam && (
          <FieldRow icon={FolderOpen} label={t("review.sharedLabel")}>
            {sharedEnabled ? (
              <span>{t("review.sharedOn")}</span>
            ) : (
              <span className="dim">{t("review.sharedOff")}</span>
            )}
          </FieldRow>
        )}

        <SupervisorRow label={t("review.supervisorLabel")} value={supervisor} />
        {showCoSupervisor && (
          <SupervisorRow
            label={t("review.coSupervisorLabel")}
            value={coSupervisor}
          />
        )}
        {!supervisor.name.trim() && !showCoSupervisor && (
          <FieldRow icon={UserCheck} label={t("review.supervisorLabel")}>
            <span className="dim">{t("review.noSupervisor")}</span>
          </FieldRow>
        )}
      </div>

      {/* Documents to create */}
      <div className="card" style={{ padding: 14 }}>
        <div
          className="flex items-center justify-between"
          style={{ marginBottom: 10 }}
        >
          <strong style={{ fontSize: 12.5 }}>
            {t("review.documentsTitle")}
          </strong>
          <span className="mono dim" style={{ fontSize: 11 }}>
            {t("review.documentsCount", { count: documents.length })}
          </span>
        </div>
        {documents.length === 0 ? (
          <div className="dim" style={{ fontSize: 12 }}>
            {t("review.loadingStructure")}
          </div>
        ) : (
          <div className="flex flex-col" style={{ gap: 2 }}>
            {documents.map((d) => {
              const code =
                d.code[lang] ?? d.code.ru ?? d.code.en ?? d.id.toUpperCase();
              const name = d.name[lang] ?? d.name.ru ?? d.name.en ?? d.id;
              return (
                <div
                  key={d.id}
                  className="flex items-center"
                  style={{
                    gap: 10,
                    padding: "5px 0",
                    fontSize: 12,
                    minWidth: 0,
                  }}
                >
                  <span
                    className="chip mono"
                    style={{
                      width: 56,
                      justifyContent: "center",
                      flexShrink: 0,
                      fontSize: 10,
                    }}
                  >
                    {code}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      color: "var(--fg-1)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      minWidth: 0,
                    }}
                  >
                    {name}
                  </span>
                  {!d.required && (
                    <span
                      className="mono dim"
                      style={{ fontSize: 10, flexShrink: 0 }}
                    >
                      {t("review.optionalDoc")}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main component ────────────────────────────────────────────────────────────
export const ProjectCreateWizard = () => {
  const { t } = useTranslation("projectCreate");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const {
    step,
    maxReached,
    packId,
    templateId,
    version,
    kind,
    title,
    folder,
    lang,
    presVariant,
    authors,
    sharedEnabled,
    supervisor,
    coSupervisor,
    coSupervisorEnabled,
    nda,
    meta,
    nextStep,
    prevStep,
    goToStep,
    setField,
    reset,
  } = useCreateWizard();

  // Prefill folder from ?folder= when arriving from connect → "Create here".
  useEffect(() => {
    const prefill = searchParams.get("folder");
    if (prefill && folder === "") {
      setField("folder", prefill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const { mutateAsync: createProject, isPending } = useCreateProject();

  const { data: versionDetail } = useVersionDetail(
    packId ?? "",
    templateId ?? "",
    version ?? "",
  );

  // Seed pack defaults + computed `auto` values (degree type, programme, defense
  // year…) into the meta state as soon as the chosen version loads, so the
  // create-step fields arrive already filled and editable. Only untouched keys
  // are filled (see seedMetaDefaults), so navigating back never clobbers edits.
  useEffect(() => {
    if (!versionDetail) return;
    const patch = seedMetaDefaults(versionDetail.meta_fields, meta);
    if (Object.keys(patch).length > 0) {
      setField("meta", { ...meta, ...patch });
    }
  }, [versionDetail, meta, setField]);

  // Create-time required fields the wizard enforces before letting the user
  // advance/finish: at least one author, the научный руководитель (when the
  // pack requires it), and every create-required text meta field.
  //
  // `versionLoaded` gates the supervisor/meta steps: until the template's
  // meta_fields are known, `createRequiredKeys` is [] (so metaComplete would be
  // vacuously true) and supervisorRequired is false — without this guard the
  // user could advance/Create with the required fields still blank.
  const versionLoaded = versionDetail !== undefined;
  const metaFields = versionDetail?.meta_fields ?? {};
  const createRequiredKeys = getCreateMetaFields(metaFields).map(
    ([key]) => key,
  );
  const supervisorRequired = isSupervisorRequired(metaFields);
  const hasAuthor = authors.some((a) => a.name.trim().length > 0);

  // Team staffing (>1 author) adds its own gates on the authors step: the pack
  // must declare "team" in supported_staffing (checked only once the version
  // detail is loaded — same versionLoaded idea as supervisor/meta), every
  // соавтор needs a ФИО, managed authors need a topic (their part of the
  // system), folder slugs must be valid and unique, and at least one author
  // must be managed. Solo (a single author) keeps the old hasAuthor-only rule.
  const isTeam = authors.length > 1;
  const supportsTeam = (versionDetail?.supported_staffing ?? ["solo"]).includes(
    "team",
  );
  const slugsValid =
    authors.every((a) => isValidSlug(a.slug)) &&
    new Set(authors.map((a) => a.slug)).size === authors.length;
  const teamComplete =
    !isTeam ||
    (versionLoaded &&
      supportsTeam &&
      authors.every((a) => a.name.trim().length > 0) &&
      authors.every((a) => !a.managed || a.topic.trim().length > 0) &&
      slugsValid &&
      authors.some((a) => a.managed));
  const authorsValid = hasAuthor && teamComplete;

  const supervisorComplete =
    !supervisorRequired || supervisor.name.trim().length > 0;
  const metaComplete = createRequiredKeys.every(
    (key) => !isMetaValueBlank(meta[key]),
  );

  // Gate «Далее» by step ID (not index) so inserting/reordering steps — e.g. the
  // «Презентация» step — never silently shifts another step's validation.
  const isStepValid = (() => {
    switch (STEPS[step]?.id) {
      case "pack":
        return !!packId;
      case "template":
        return !!templateId;
      case "version":
        return !!version;
      case "folder":
        return title.trim().length > 0 && folder.trim().length > 0;
      case "authors":
        return authorsValid;
      case "supervisor":
        return versionLoaded && supervisorComplete;
      case "meta":
        return versionLoaded && metaComplete;
      default:
        return true;
    }
  })();

  const handleCreate = async () => {
    if (
      !packId ||
      !templateId ||
      !version ||
      !folder ||
      !title.trim() ||
      !versionLoaded ||
      !authorsValid ||
      !supervisorComplete ||
      !metaComplete
    )
      return;

    // The LaTeX title block reads `project.meta.group`; we don't show this
    // field in the wizard anymore, so backfill it from the first non-empty
    // author group. If nobody filled a group, the title block degrades to
    // an empty cell — same as before authors had per-row groups.
    const firstAuthorGroup =
      authors.find((a) => a.group.trim() !== "")?.group.trim() ?? "";
    const mergedMeta = {
      ...meta,
      ...(firstAuthorGroup ? { group: firstAuthorGroup } : {}),
      ...(nda ? { nda: true } : {}),
    };

    const payload = {
      name: title.trim(),
      folder,
      pack_id: packId,
      template_id: templateId,
      version,
      engine: "xelatex" as const,
      kind,
      staffing: isTeam ? ("team" as const) : ("solo" as const),
      lang,
      // Chosen presentation format; omitted → backend uses the first variant.
      ...(presVariant ? { pres_variant: presVariant } : {}),
      // The backend has its own translit fallback for missing slugs, but the
      // wizard always sends the slug it shows — the user may have edited it.
      // Blank slug/topic degrade to null so solo authors created before the
      // team fields existed keep the exact old payload semantics.
      authors: authors.map((a) => ({
        name: a.name,
        group: a.group,
        slug: a.slug.trim() !== "" ? a.slug : null,
        topic: a.topic.trim() !== "" ? a.topic.trim() : null,
        managed: a.managed,
      })),
      // The shared/ toggle only exists on the team step; if the user flipped it
      // and then dropped back to a single author, don't leak the stale value.
      shared_enabled: isTeam ? sharedEnabled : true,
      supervisor: supervisor.name.trim()
        ? {
            name: supervisor.name,
            title: supervisor.title,
            role: supervisor.role,
            ...(supervisor.degree ? { degree: supervisor.degree } : {}),
          }
        : null,
      co_supervisor:
        coSupervisorEnabled && coSupervisor.name.trim()
          ? {
              name: coSupervisor.name,
              title: coSupervisor.title,
              role: coSupervisor.role,
              ...(coSupervisor.degree ? { degree: coSupervisor.degree } : {}),
            }
          : null,
      meta: mergedMeta,
    };

    try {
      const project = await createProject(payload);
      reset();
      void navigate(`/projects/${project.id}/documents`);
    } catch {
      // Toaster already shown by axios interceptor; stay on review step so the
      // user can fix the issue and retry.
    }
  };

  const steps = [
    <StepPack key="pack" />,
    <StepTemplate key="template" />,
    <StepVersion key="version" />,
    <StepKind key="kind" />,
    <StepFolder key="folder" />,
    <StepLang key="lang" />,
    <StepPresentation key="presentation" />,
    <StepAuthors key="authors" />,
    <StepSupervisor key="supervisor" />,
    <StepMeta key="meta" />,
    <StepReview key="review" />,
  ];

  const cur: StepDef = STEPS[step] ?? STEPS[0] ?? { id: "pack", icon: Layers };
  const CurIcon = cur.icon;
  const isLastStep = step === TOTAL_STEPS - 1;

  return (
    <div className="flex h-full" style={{ background: "var(--bg-0)" }}>
      {/* Sidebar */}
      <div
        className="flex flex-col shrink-0"
        style={{
          width: 220,
          padding: "20px 8px 24px",
          background: "var(--bg-1)",
          borderRight: "1px solid var(--border)",
          overflowY: "auto",
        }}
      >
        <div
          className="flex items-center gap-2"
          style={{ padding: "0 12px 16px" }}
        >
          <Logomark />
          <div className="flex flex-col" style={{ gap: 0, minWidth: 0 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              {t("wizard.newProject")}
            </div>
            <div
              className="mono dim"
              style={{ fontSize: 10, whiteSpace: "nowrap" }}
            >
              {t("wizard.stepCounter", {
                current: step + 1,
                total: TOTAL_STEPS,
              })}
            </div>
          </div>
        </div>

        {STEPS.map((s, i) => {
          const done = i < step;
          const active = i === step;
          const reachable = i <= maxReached;
          const idleColor = done
            ? "var(--fg-1)"
            : reachable
              ? "var(--fg-3)"
              : "var(--fg-3)";
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => {
                goToStep(i);
              }}
              disabled={!reachable}
              aria-current={active ? "step" : undefined}
              title={reachable ? undefined : t("wizard.lockedStepTitle")}
              className="flex items-center gap-2"
              style={{
                width: "100%",
                padding: "6px 14px",
                color: active ? "var(--fg-0)" : idleColor,
                fontSize: 12.5,
                position: "relative",
                background: "transparent",
                border: 0,
                cursor: reachable ? "pointer" : "not-allowed",
                textAlign: "left",
                opacity: reachable ? 1 : 0.5,
                transition: "background 0.08s, color 0.08s",
              }}
              onMouseEnter={(e) => {
                if (!active && reachable) {
                  e.currentTarget.style.background = "var(--bg-hover)";
                  e.currentTarget.style.color = "var(--fg-0)";
                }
              }}
              onMouseLeave={(e) => {
                if (!active && reachable) {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.color = done
                    ? "var(--fg-1)"
                    : "var(--fg-3)";
                }
              }}
            >
              {active && (
                <span
                  style={{
                    position: "absolute",
                    left: 0,
                    top: 4,
                    bottom: 4,
                    width: 3,
                    background: "var(--accent)",
                    borderRadius: "0 999px 999px 0",
                  }}
                />
              )}
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: "50%",
                  background: active
                    ? "var(--accent)"
                    : done
                      ? "var(--c-ok-soft)"
                      : "var(--bg-2)",
                  color: active
                    ? "var(--accent-ink)"
                    : done
                      ? "var(--c-ok)"
                      : "var(--fg-3)",
                  border:
                    "1px solid " + (active ? "transparent" : "var(--border)"),
                  fontSize: 10,
                  fontFamily: "var(--font-mono)",
                  fontWeight: 600,
                }}
              >
                {done ? <Check size={11} /> : i + 1}
              </div>
              <span>{t(`steps.${s.id}.title`)}</span>
            </button>
          );
        })}
      </div>

      {/* Right pane */}
      <div className="flex-1 flex flex-col" style={{ minWidth: 0 }}>
        <div style={{ padding: "20px 28px 8px" }}>
          <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
            <CurIcon size={14} style={{ color: "var(--accent)" }} />
            <span
              className="mono"
              style={{
                fontSize: 10,
                color: "var(--accent)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              {t("wizard.stepBadge", { current: step + 1, total: TOTAL_STEPS })}
            </span>
          </div>
          <h2
            style={{
              margin: "0 0 4px",
              fontSize: 18,
              fontWeight: 600,
              letterSpacing: "-0.01em",
            }}
          >
            {t(`steps.${cur.id}.title`)}
          </h2>
          <p
            className="dim"
            style={{ margin: 0, fontSize: 12.5, maxWidth: 560 }}
          >
            {t(`steps.${cur.id}.sub`)}
          </p>
        </div>

        <div
          className="flex-1"
          style={{
            padding: "20px 28px 24px",
            overflowY: "auto",
            overflowX: "hidden",
            minWidth: 0,
          }}
        >
          {steps[step]}
        </div>

        <div
          className="flex items-center justify-between"
          style={{
            padding: "12px 20px",
            borderTop: "1px solid var(--border)",
            background: "var(--bg-1)",
          }}
        >
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              reset();
              void navigate("/");
            }}
          >
            {t("wizard.cancel")}
          </button>

          <div className="flex gap-2">
            <button
              type="button"
              className="btn"
              disabled={step === 0}
              onClick={prevStep}
            >
              <ArrowLeft size={12} />
              {t("wizard.back")}
            </button>
            {!isLastStep ? (
              <button
                type="button"
                className="btn primary"
                onClick={nextStep}
                disabled={!isStepValid}
              >
                {t("wizard.next")}
                <ArrowRight size={12} />
              </button>
            ) : (
              <button
                type="button"
                className="btn primary"
                onClick={() => void handleCreate()}
                disabled={
                  isPending ||
                  !packId ||
                  !templateId ||
                  !version ||
                  !folder ||
                  !title.trim() ||
                  !versionLoaded ||
                  !authorsValid ||
                  !supervisorComplete ||
                  !metaComplete
                }
              >
                {isPending ? (
                  <Loader2 size={12} className="spin" />
                ) : (
                  <Check size={12} />
                )}
                {t("wizard.create")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
