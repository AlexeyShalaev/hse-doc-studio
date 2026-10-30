import { Fragment, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { i18n } from "@shared/lib";
import {
  Bot,
  Building2,
  Cpu,
  DatabaseBackup,
  Drama,
  HardDrive,
  Info,
  KeyRound,
  ListChecks,
  Presentation,
  Search,
  ShieldCheck,
  Sliders,
  Terminal,
  Type,
  UserCircle,
  UserRound,
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
import { AccountSection } from "@features/account-settings";
import { AuthorProfileSection } from "@features/author-profile";
import { ExportImportSection } from "@features/export-import";
import { GitAccessSection } from "@features/git-remote";
import { MyOrganizationsSection } from "@features/my-organizations";
import {
  LOCAL_BOOTSTRAP,
  useBootstrap,
  useCapabilities,
} from "@entities/session";
import type { Capabilities } from "@entities/session";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";

/**
 * Чьи это настройки. user: личные, видны всем. installation: уровень установки,
 * в серверном режиме их место в админке, а в локальном человек и есть владелец.
 * local-only: про машину пользователя (диск, локальные модели, выгрузка данных),
 * на сервере смысла не имеют. Область совпадает с SettingScope бэкенда: пока
 * реестр не отдаётся в bootstrap, она записана здесь, а видимость решает
 * возможность клиента, а не режим.
 */
type SectionScope = "user" | "installation" | "local-only";

type SectionDef = {
  id: SettingsSectionId;
  labelKey: string;
  icon: LucideIcon;
  group: SectionGroupId;
  scope: SectionScope;
  /** Раздел виден, только если у клиента есть эта возможность. */
  requires?: keyof Capabilities;
  /**
   * Раздел зависит от того, есть ли у клиента аккаунт (вошедший пользователь):
   * "with" только с ним, "without" только без него. Подпись версий на сервере
   * живёт в аккаунте, поэтому второго профиля автора рядом нет.
   */
  account?: "with" | "without";
};

/** Раздел доступен при данных возможностях: личные всегда, остальные по requires. */
const isSectionAvailable = (
  def: Pick<SectionDef, "scope" | "requires" | "account">,
  has: (name: keyof Capabilities) => boolean,
  hasAccount: boolean,
): boolean =>
  (def.requires === undefined || has(def.requires)) &&
  (def.account === undefined || (def.account === "with") === hasAccount);

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
    scope: "user",
    labelKey: "settingsPage.sections.appearance",
    icon: Sliders,
  },
  {
    id: "account",
    group: "general",
    scope: "user",
    account: "with",
    labelKey: "settingsPage.sections.account",
    icon: UserCircle,
  },
  {
    id: "organizations",
    group: "general",
    scope: "user",
    account: "with",
    labelKey: "settingsPage.sections.organizations",
    icon: Building2,
  },
  {
    id: "profile",
    group: "general",
    scope: "user",
    account: "without",
    labelKey: "settingsPage.sections.profile",
    icon: UserRound,
  },
  {
    id: "compiler",
    group: "documents",
    scope: "installation",
    requires: "docker_ui",
    labelKey: "settingsPage.sections.compiler",
    icon: Terminal,
  },
  {
    id: "fonts",
    group: "documents",
    scope: "installation",
    requires: "docker_ui",
    labelKey: "settingsPage.sections.fonts",
    icon: Type,
  },
  {
    id: "checks",
    group: "documents",
    scope: "user",
    labelKey: "settingsPage.sections.checks",
    icon: ListChecks,
  },
  {
    id: "presentations",
    group: "documents",
    scope: "user",
    requires: "docker_ui",
    labelKey: "settingsPage.sections.presentations",
    icon: Presentation,
  },
  {
    id: "signing",
    group: "documents",
    scope: "user",
    labelKey: "settingsPage.sections.signing",
    icon: ShieldCheck,
  },
  {
    id: "providers",
    group: "ai",
    scope: "user",
    labelKey: "settingsPage.sections.providers",
    icon: Bot,
  },
  {
    id: "local-models",
    group: "ai",
    scope: "local-only",
    requires: "local_services_ui",
    labelKey: "settingsPage.sections.localModels",
    icon: Cpu,
  },
  {
    id: "agent-personas",
    group: "ai",
    scope: "user",
    labelKey: "settingsPage.sections.agentPersonas",
    icon: Drama,
  },
  {
    id: "disk",
    group: "system",
    scope: "local-only",
    requires: "docker_ui",
    labelKey: "settingsPage.sections.disk",
    icon: HardDrive,
  },
  {
    id: "data",
    group: "system",
    scope: "local-only",
    requires: "local_services_ui",
    labelKey: "settingsPage.sections.data",
    icon: DatabaseBackup,
  },
  {
    id: "git-access",
    group: "system",
    scope: "user",
    labelKey: "settingsPage.sections.gitAccess",
    icon: KeyRound,
  },
  {
    id: "about",
    group: "system",
    scope: "user",
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
    case "account":
      return <AccountSection />;
    case "organizations":
      return <MyOrganizationsSection />;
    case "profile":
      return <AuthorProfileSection />;
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
    case "git-access":
      return <GitAccessSection />;
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

  // Пока bootstrap не пришёл (шлюз приложения его уже ждёт, так что в работе
  // он есть всегда), считаем клиента локальным: так страница в тестах и
  // галереях ведёт себя как раньше.
  const { capabilities } = useCapabilities();
  const caps = capabilities ?? LOCAL_BOOTSTRAP.capabilities;
  const hasAccount = useBootstrap().data?.user != null;
  const visibleSections = SECTIONS.filter((s) =>
    isSectionAvailable(s, (name) => caps[name], hasAccount),
  );
  const visibleIds = new Set<SettingsSectionId>(
    visibleSections.map((s) => s.id),
  );

  const active = visibleSections.find((s) => s.id === section);
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
    // Прямая ссылка на скрытый раздел ведёт на первый доступный, а не на пустую страницу.
    const fallback = visibleIds.has(DEFAULT_SECTION)
      ? DEFAULT_SECTION
      : (visibleSections[0]?.id ?? DEFAULT_SECTION);
    return <Navigate to={`/settings/${fallback}`} replace />;
  }

  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const isSearching = tokens.length > 0;
  const results = isSearching
    ? SETTINGS_SEARCH_INDEX.filter(
        (entry) =>
          visibleIds.has(entry.sectionId) && matchesQuery(entry, tokens),
      )
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
                {visibleSections.map((s, index) => {
                  const Icon = s.icon;
                  const isActive = s.id === active.id;
                  // Заголовок печатается на первом разделе группы: список
                  // объявлен уже сгруппированным, поэтому достаточно сравнить
                  // с предыдущим — отдельная вложенная структура тут лишняя.
                  const isGroupStart =
                    visibleSections[index - 1]?.group !== s.group;
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
