import { Fragment, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { i18n } from "@shared/lib";
import {
  Bot,
  Cpu,
  DatabaseBackup,
  Drama,
  HardDrive,
  Info,
  ListChecks,
  Presentation,
  Search,
  ShieldCheck,
  Sliders,
  Terminal,
  Type,
  X,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import {
  AboutSection,
  AgentPersonasSection,
  AppearanceSection,
  ChecksSection,
  CompilerSection,
  DiskUsageSection,
  FontsSection,
  ImagesSection,
  LocalModelsSection,
  OfficeServicesSection,
  ProvidersSection,
  SigningIdentitiesSection,
  SETTINGS_SEARCH_INDEX,
  type SettingSearchEntry,
  type SettingsSectionId,
} from "@widgets/settings";
import { ExportImportSection } from "@features/export-import";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";

type SectionDef = {
  id: SettingsSectionId;
  labelKey: string;
  icon: LucideIcon;
  group: SectionGroupId;
};

/**
 * Группы разделов. Список из двенадцати пунктов без структуры читается как
 * свалка: «Провайдеры», «Локальные модели» и «Роли агента» — про одно и то же,
 * а стояли вперемешку с дисками и шрифтами.
 */
const SECTION_GROUPS = {
  general: "settingsPage.groups.general",
  documents: "settingsPage.groups.documents",
  ai: "settingsPage.groups.ai",
  system: "settingsPage.groups.system",
} as const;

type SectionGroupId = keyof typeof SECTION_GROUPS;

const SECTIONS: readonly SectionDef[] = [
  {
    id: "appearance",
    group: "general",
    labelKey: "settingsPage.sections.appearance",
    icon: Sliders,
  },
  {
    id: "compiler",
    group: "documents",
    labelKey: "settingsPage.sections.compiler",
    icon: Terminal,
  },
  {
    id: "fonts",
    group: "documents",
    labelKey: "settingsPage.sections.fonts",
    icon: Type,
  },
  {
    id: "checks",
    group: "documents",
    labelKey: "settingsPage.sections.checks",
    icon: ListChecks,
  },
  {
    id: "presentations",
    group: "documents",
    labelKey: "settingsPage.sections.presentations",
    icon: Presentation,
  },
  {
    id: "signing",
    group: "documents",
    labelKey: "settingsPage.sections.signing",
    icon: ShieldCheck,
  },
  {
    id: "providers",
    group: "ai",
    labelKey: "settingsPage.sections.providers",
    icon: Bot,
  },
  {
    id: "local-models",
    group: "ai",
    labelKey: "settingsPage.sections.localModels",
    icon: Cpu,
  },
  {
    id: "agent-personas",
    group: "ai",
    labelKey: "settingsPage.sections.agentPersonas",
    icon: Drama,
  },
  {
    id: "disk",
    group: "system",
    labelKey: "settingsPage.sections.disk",
    icon: HardDrive,
  },
  {
    id: "data",
    group: "system",
    labelKey: "settingsPage.sections.data",
    icon: DatabaseBackup,
  },
  {
    id: "about",
    group: "system",
    labelKey: "settingsPage.sections.about",
    icon: Info,
  },
];

const DEFAULT_SECTION: SettingsSectionId = "appearance";

// Highlight timing for the "jump to setting" flash. Settings sections fetch
// their own data, so the target element can mount a few frames after we
// navigate — we retry getElementById for a short window before giving up.
const FLASH_DURATION_MS = 1400;
const ANCHOR_RETRY_MS = 60;
const MAX_ANCHOR_ATTEMPTS = 25;

const renderSection = (id: SettingsSectionId) => {
  switch (id) {
    case "appearance":
      return <AppearanceSection />;
    case "compiler":
      return (
        <>
          <CompilerSection />
          <ImagesSection />
        </>
      );
    case "fonts":
      return <FontsSection />;
    case "checks":
      return <ChecksSection />;
    case "presentations":
      return <OfficeServicesSection />;
    case "providers":
      return <ProvidersSection />;
    case "local-models":
      return <LocalModelsSection />;
    case "agent-personas":
      return <AgentPersonasSection />;
    case "signing":
      return <SigningIdentitiesSection />;
    case "disk":
      return <DiskUsageSection />;
    case "data":
      return <ExportImportSection />;
    case "about":
      return <AboutSection />;
  }
};

const sectionLabel = (id: SettingsSectionId): string => {
  const def = SECTIONS.find((s) => s.id === id);
  return def ? i18n.t(def.labelKey, { ns: "appChrome" }) : "";
};

const matchesQuery = (entry: SettingSearchEntry, tokens: string[]): boolean => {
  const haystack = [
    i18n.t(entry.labelKey, { ns: "settings" }),
    sectionLabel(entry.sectionId),
    ...(entry.keywords ?? []),
  ]
    .join(" ")
    .toLowerCase();
  return tokens.every((token) => haystack.includes(token));
};

export const SettingsPage = () => {
  const { t } = useTranslation("appChrome");
  const navigate = useNavigate();
  const { section } = useParams<{ section: string }>();
  const [query, setQuery] = useState("");
  // A new object (bumped nonce) on every result click so the scroll/flash effect
  // re-runs even when the same setting is clicked twice in a row.
  const [flash, setFlash] = useState<{
    anchorId: string;
    nonce: number;
  } | null>(null);

  const active = SECTIONS.find((s) => s.id === section);
  const activeId = active?.id;

  useEffect(() => {
    if (!flash || !activeId) return;

    let cancelled = false;
    let attempts = 0;
    let retryTimer: number | undefined;
    let clearTimer: number | undefined;

    const tryScroll = () => {
      if (cancelled) return;
      const el = document.getElementById(flash.anchorId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        el.classList.add("setting-flash");
        clearTimer = window.setTimeout(() => {
          el.classList.remove("setting-flash");
        }, FLASH_DURATION_MS);
        return;
      }
      attempts += 1;
      if (attempts < MAX_ANCHOR_ATTEMPTS) {
        retryTimer = window.setTimeout(tryScroll, ANCHOR_RETRY_MS);
      }
    };
    tryScroll();

    return () => {
      cancelled = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (clearTimer) window.clearTimeout(clearTimer);
      document
        .getElementById(flash.anchorId)
        ?.classList.remove("setting-flash");
    };
  }, [flash, activeId]);

  if (!active) {
    return <Navigate to={`/settings/${DEFAULT_SECTION}`} replace />;
  }

  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const isSearching = tokens.length > 0;
  const results = isSearching
    ? SETTINGS_SEARCH_INDEX.filter((entry) => matchesQuery(entry, tokens))
    : [];

  const handleQueryChange = (value: string) => {
    setQuery(value);
    if (value.trim() === "") setFlash(null);
  };

  const handleResultClick = (entry: SettingSearchEntry) => {
    if (entry.sectionId !== active.id) {
      void navigate(`/settings/${entry.sectionId}`, { replace: true });
    }
    setFlash((prev) => ({
      anchorId: entry.anchorId,
      nonce: (prev?.nonce ?? 0) + 1,
    }));
  };

  const handleClose = () => {
    if (window.history.length > 1) {
      void navigate(-1);
    } else {
      void navigate("/");
    }
  };

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />

      <div className="flex-1" />
      <AppStatusBar />

      <div className="settings-modal-overlay" onClick={handleClose}>
        <div
          className="settings-modal"
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          <aside className="settings-modal-sidebar">
            <div className="settings-modal-title">
              {t("settingsPage.title")}
            </div>
            <div className="settings-modal-search">
              <Search size={15} />
              <input
                type="text"
                value={query}
                onChange={(e) => {
                  handleQueryChange(e.target.value);
                }}
                placeholder={t("settingsPage.searchPlaceholder")}
              />
            </div>

            {isSearching ? (
              <div className="settings-modal-results">
                {results.length === 0 ? (
                  <div className="settings-modal-empty">
                    {t("settingsPage.empty")}
                  </div>
                ) : (
                  results.map((entry) => {
                    const def = SECTIONS.find((s) => s.id === entry.sectionId);
                    const Icon = def?.icon ?? Search;
                    return (
                      <button
                        key={entry.anchorId}
                        type="button"
                        className="settings-modal-result"
                        onClick={() => {
                          handleResultClick(entry);
                        }}
                      >
                        <Icon size={14} />
                        <span className="settings-modal-result-text">
                          <span className="settings-modal-result-label">
                            {t(entry.labelKey, { ns: "settings" })}
                          </span>
                          <span className="settings-modal-result-section">
                            {def ? t(def.labelKey) : null}
                          </span>
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            ) : (
              <nav className="settings-modal-nav">
                {SECTIONS.map((s, index) => {
                  const Icon = s.icon;
                  const isActive = s.id === active.id;
                  // Заголовок печатается на первом разделе группы: список
                  // объявлен уже сгруппированным, поэтому достаточно сравнить
                  // с предыдущим — отдельная вложенная структура тут лишняя.
                  const isGroupStart = SECTIONS[index - 1]?.group !== s.group;
                  return (
                    <Fragment key={s.id}>
                      {isGroupStart && (
                        <div className="settings-modal-group">
                          {t(SECTION_GROUPS[s.group])}
                        </div>
                      )}
                      <Link
                        to={`/settings/${s.id}`}
                        replace
                        className={clsx(
                          "settings-modal-link",
                          isActive && "active",
                        )}
                      >
                        <Icon size={15} />
                        <span>{t(s.labelKey)}</span>
                      </Link>
                    </Fragment>
                  );
                })}
              </nav>
            )}
          </aside>

          <section className="settings-modal-main">
            <button
              type="button"
              className="icon-btn settings-modal-close"
              aria-label={t("settingsPage.close")}
              onClick={handleClose}
            >
              <X size={17} />
            </button>

            <div className="settings-modal-content">
              {renderSection(active.id)}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};
