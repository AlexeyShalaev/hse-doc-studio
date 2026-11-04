import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  FileArchive,
  GitBranch,
  History,
  Plus,
  Search,
  Server,
  Upload,
} from "lucide-react";
import { clsx } from "clsx";
import type { z } from "zod";
import {
  buildCloudList,
  useCloudProjects,
  type CloudEntry,
} from "@entities/git-server";
import { CLONE_PATH } from "@entities/git-sync";
import {
  CONNECT_SERVER_PATH,
  LOCAL_STUDIO_PATH,
  connectServerPath,
} from "@entities/local-studio";
import { useBootstrap, useCapabilities } from "@entities/session";
import type { ProjectResponseSchema } from "@entities/project";
import {
  useProjects,
  useTemplateMeta,
  useUpdateProject,
} from "@entities/project";
import { ProjectImportDialog } from "@features/project-import";
import {
  useIsPhoneWidth,
  useRecentProjectIds,
  useWorkspaceStore,
} from "@shared/lib";
import { FilterSheet, FilterSheetGroup } from "@shared/ui/FilterSheet";
import { Spinner } from "@shared/ui/Spinner";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { ChatDock } from "@widgets/ChatDock";
import { CloudNotices } from "./CloudNotices";
import { CloudOpenDialog } from "./CloudOpenDialog";
import { CloudProjectCard } from "./CloudProjectCard";
import { EmptyState } from "./EmptyState";
import { LoadError } from "./LoadError";
import { NewProjectCard } from "./NewProjectCard";
import { ProjectCard } from "./ProjectCard";
import { RecentActivity } from "./RecentActivity";

type FilterType = "active" | "all" | "archived";
/** Чьи проекты: только на сервере, где у проекта есть владелец. */
type ScopeType = "all" | "mine" | "orgs";
type SortMode = "recent" | "pinned" | "name";
type ProjectItem = z.infer<typeof ProjectResponseSchema>;

const SORT_STORAGE_KEY = "hse-studio.welcome.sort";
/** Полоска «Недавние» — быстрый возврат, а не второй список всех проектов. */
const RECENT_STRIP_LIMIT = 5;
/** Атрибут, по которому стрелки находят карточки в гриде. */
const CARD_SELECTOR = "[data-project-card]";
const GRID_NAV_KEYS = [
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
  "Home",
  "End",
];

const isSortMode = (value: string | null): value is SortMode =>
  value === "recent" || value === "pinned" || value === "name";

const readStoredSortMode = (): SortMode => {
  try {
    const stored = window.localStorage.getItem(SORT_STORAGE_KEY);
    return isSortMode(stored) ? stored : "recent";
  } catch {
    // Приватный режим — просто стартуем с порядка по умолчанию.
    return "recent";
  }
};

/** Фокус в поле, textarea или contenteditable — «/» там обычный символ. */
const isTypingTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
};

type RecentProjectTileProps = {
  project: ProjectItem;
  onOpen: () => void;
};

const RecentProjectTile = ({ project, onOpen }: RecentProjectTileProps) => {
  const meta = useTemplateMeta(project);
  const Icon = meta.icon;
  const hue = String(meta.accentHue);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="card hover flex items-center text-left"
      style={{
        gap: "0.625rem",
        padding: "0.5625rem 0.75rem",
        flex: "1 1 13.125rem",
        maxWidth: "18.75rem",
        minWidth: 0,
      }}
    >
      <span
        className="flex items-center justify-center shrink-0"
        style={{
          width: "1.625rem",
          height: "1.625rem",
          borderRadius: "0.4375rem",
          background: `oklch(60% 0.16 ${hue} / 0.14)`,
          color: `oklch(70% 0.16 ${hue})`,
        }}
      >
        <Icon size="0.8125rem" />
      </span>
      {/* minWidth инлайном: утилита min-w-0 в этой сборке Tailwind не рождается. */}
      <span className="flex flex-col" style={{ minWidth: 0, gap: 1 }}>
        <span
          className="truncate text-fg-0"
          style={{ fontSize: "0.78125rem", fontWeight: 500 }}
        >
          {project.name}
        </span>
        {/* На сервере папки нет: под названием владелец проекта. */}
        <span
          className={clsx("truncate", project.folder !== "" && "mono")}
          style={{ fontSize: "0.625rem", color: "var(--fg-3)" }}
        >
          {project.folder !== "" ? project.folder : project.owner?.name}
        </span>
      </span>
    </button>
  );
};

/** На телефоне у группы фильтров видимая подпись (шторка), на десктопе её нет: ряд как был. */
const FilterGroup = ({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) => {
  const isPhone = useIsPhoneWidth();
  return isPhone ? (
    <FilterSheetGroup label={label}>{children}</FilterSheetGroup>
  ) : (
    <>{children}</>
  );
};

export const WelcomePage = () => {
  const { t, i18n } = useTranslation("welcome");
  const navigate = useNavigate();
  const { t: tAccess } = useTranslation("projectAccess");
  const { t: tImport } = useTranslation("projectImport");
  const { t: tLocal } = useTranslation("localStudio");
  const {
    data: projects,
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useProjects();
  const { lacks, has } = useCapabilities();
  const user = useBootstrap().data?.user ?? null;
  // Папок на диске нет там, где bootstrap так сказал: проекты лежат на сервере.
  const isServerList = lacks("fs_browse");
  const canConnectFolder = !lacks("connect_folder");
  // Облачные проекты видны только в локальной Студии, которая умеет входить на сервер.
  const showCloud = !isServerList && has("git_server_login");
  const cloud = useCloudProjects(showCloud);
  const { mutate: updateProject } = useUpdateProject();
  const recentIds = useRecentProjectIds();
  // The one unified agent, docked between the title and status bars (same
  // panel as in a project — here it has no project bound, so app/system tools).
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);

  const [query, setQuery] = useState("");
  const isPhone = useIsPhoneWidth();
  const [filter, setFilter] = useState<FilterType>("active");
  const [scope, setScope] = useState<ScopeType>("all");
  const [sort, setSort] = useState<SortMode>(readStoredSortMode);
  const [importOpen, setImportOpen] = useState(false);
  const [opening, setOpening] = useState<CloudEntry | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  // Подсказка «/» рядом с полем поиска висела без обработчика — вешаем его.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const collator = useMemo(
    () => new Intl.Collator(i18n.language),
    [i18n.language],
  );

  /** id → место в истории переходов; чем меньше, тем свежее. */
  const recentRank = useMemo(
    () => new Map(recentIds.map((id, index) => [id, index] as const)),
    [recentIds],
  );

  const filtered = useMemo(() => {
    let xs = projects ?? [];

    if (filter === "active") xs = xs.filter((p) => !p.archived);
    else if (filter === "archived") xs = xs.filter((p) => p.archived);

    if (scope === "mine") {
      xs = xs.filter((p) => p.owner?.kind !== "org");
    } else if (scope === "orgs") {
      xs = xs.filter((p) => p.owner?.kind === "org");
    }

    if (query.trim()) {
      const ql = query.trim().toLowerCase();
      xs = xs.filter(
        (p) =>
          p.name.toLowerCase().includes(ql) ||
          p.folder.toLowerCase().includes(ql) ||
          (p.owner?.name ?? "").toLowerCase().includes(ql) ||
          (p.supervisor?.name ?? "").toLowerCase().includes(ql),
      );
    }

    const byName = (a: ProjectItem, b: ProjectItem): number =>
      collator.compare(a.name, b.name);

    return [...xs].sort((a, b) => {
      if (sort === "name") return byName(a, b);
      if (sort === "pinned") {
        const byPin = (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
        return byPin === 0 ? byName(a, b) : byPin;
      }
      // «Недавние»: сначала то, что человек реально открывал, потом всё
      // остальное по алфавиту. Сортировать по updated_at нельзя — это mtime
      // папки, он дёргается на каждой сборке и карточки бы прыгали.
      const rankA = recentRank.get(a.id) ?? Number.MAX_SAFE_INTEGER;
      const rankB = recentRank.get(b.id) ?? Number.MAX_SAFE_INTEGER;
      return rankA === rankB ? byName(a, b) : rankA - rankB;
    });
  }, [projects, filter, scope, query, sort, collator, recentRank]);

  const cloudView = useMemo(
    () =>
      buildCloudList(
        cloud.data?.servers ?? [],
        new Set((projects ?? []).map((p) => p.id.toLowerCase())),
      ),
    [cloud.data, projects],
  );

  // Облачные проекты, которых нет на компьютере, идут в общем списке после локальных; поиск и вкладка
  // «Архив» действуют и на них (архива в облаке нет, там они не показываются).
  const cloudVisible = useMemo(() => {
    if (!showCloud || filter === "archived") return [];
    const ql = query.trim().toLowerCase();
    return cloudView.remote
      .filter(
        ({ project, server }) =>
          ql === "" ||
          project.name.toLowerCase().includes(ql) ||
          project.owner_name.toLowerCase().includes(ql) ||
          server.host.toLowerCase().includes(ql),
      )
      .sort((a, b) => collator.compare(a.project.name, b.project.name));
  }, [showCloud, filter, query, cloudView, collator]);

  // Переключатель «Мои / Организации» нужен, только когда есть что разделять:
  // человек состоит в организации или ему уже открыли проект организации.
  const showScopeFilter =
    isServerList &&
    ((user?.org_roles.length ?? 0) > 0 ||
      (projects ?? []).some((p) => p.owner?.kind === "org"));

  const recentProjects = useMemo(() => {
    const byId = new Map((projects ?? []).map((p) => [p.id, p] as const));
    const picked: ProjectItem[] = [];
    for (const id of recentIds) {
      // Стор переживает удаление проекта — мёртвые id молча пропускаем.
      const project = byId.get(id);
      if (!project || project.archived) continue;
      picked.push(project);
      if (picked.length === RECENT_STRIP_LIMIT) break;
    }
    return picked;
  }, [projects, recentIds]);

  // Во время поиска полоска только мешает: она не подчиняется запросу.
  const isRecentStripVisible =
    recentProjects.length > 0 && query.trim() === "" && !isLoading;

  const handleOpenProject = (project: ProjectItem) => {
    // Ведём на /projects/<id> без документа: редирект сам вернёт человека к
    // последнему открытому в этом проекте документу.
    void navigate(`/projects/${project.id}`);
  };

  const handleTogglePin = (project: ProjectItem) => {
    updateProject({ id: project.id, data: { pinned: !project.pinned } });
  };

  const handleToggleArchive = (project: ProjectItem) => {
    updateProject({ id: project.id, data: { archived: !project.archived } });
  };

  const handleCreateProject = () => {
    void navigate("/wizard?mode=create");
  };

  const handleConnectFolder = () => {
    void navigate("/wizard?mode=connect");
  };

  const handleCloneFromGit = () => {
    void navigate(CLONE_PATH);
  };

  // Облако ведёт на «Локальную версию», локальная Студия на «Подключиться к серверу».
  const canConnectServer = has("git_server_login");
  const handleLocalStudio = isServerList
    ? () => {
        void navigate(LOCAL_STUDIO_PATH);
      }
    : canConnectServer
      ? () => {
          void navigate(CONNECT_SERVER_PATH);
        }
      : undefined;

  const handleImportArchive = () => {
    setImportOpen(true);
  };

  const handleChangeSort = (next: SortMode) => {
    setSort(next);
    try {
      window.localStorage.setItem(SORT_STORAGE_KEY, next);
    } catch {
      // Приватный режим — выбор просто не переживёт перезагрузку.
    }
  };

  const handleResetQuery = () => {
    setQuery("");
    searchRef.current?.focus();
  };

  const handleGridKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!GRID_NAV_KEYS.includes(e.key)) return;
    const grid = gridRef.current;
    if (!grid) return;
    const cards = Array.from(grid.querySelectorAll<HTMLElement>(CARD_SELECTOR));
    const index = cards.findIndex((card) => card === document.activeElement);
    // -1 == фокус внутри карточки (кнопки «закрепить»/«архив») — не мешаем.
    if (index === -1) return;
    e.preventDefault();

    // Колонок столько, сколько карточек делят верхнюю границу с первой:
    // грид auto-fill, и число колонок известно только после раскладки.
    const firstTop = cards[0]?.offsetTop;
    const columns = Math.max(
      1,
      cards.filter((card) => card.offsetTop === firstTop).length,
    );

    let next = index;
    if (e.key === "ArrowLeft") next = index - 1;
    else if (e.key === "ArrowRight") next = index + 1;
    else if (e.key === "ArrowUp") next = index - columns;
    else if (e.key === "ArrowDown") next = index + columns;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = cards.length - 1;

    cards[next]?.focus();
  };

  const segClass = isPhone ? "seg seg-fill" : "seg shrink-0";
  const filterGroups = (
    <>
      <FilterGroup label={t("filters.label")}>
        <div className={segClass} role="group" aria-label={t("filters.label")}>
          {(["active", "all", "archived"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => {
                setFilter(f);
              }}
              aria-pressed={filter === f}
              className={clsx(filter === f && "active")}
            >
              {t(`filters.${f}`)}
            </button>
          ))}
        </div>
      </FilterGroup>
      {showScopeFilter && (
        <FilterGroup label={tAccess("scope.label")}>
          <div
            className={segClass}
            role="group"
            aria-label={tAccess("scope.label")}
          >
            {(["all", "mine", "orgs"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setScope(value);
                }}
                aria-pressed={scope === value}
                className={clsx(scope === value && "active")}
              >
                {tAccess(`scope.${value}`)}
              </button>
            ))}
          </div>
        </FilterGroup>
      )}
      <FilterGroup label={t("sort.label")}>
        <div className={segClass} role="group" aria-label={t("sort.label")}>
          {(["recent", "pinned", "name"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => {
                handleChangeSort(mode);
              }}
              aria-pressed={sort === mode}
              className={clsx(sort === mode && "active")}
            >
              {t(`sort.${mode}`)}
            </button>
          ))}
        </div>
      </FilterGroup>
    </>
  );

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="welcome-page">
            <div
              className="welcome-head flex items-center justify-between"
              style={{ gap: "1rem", flexWrap: "wrap" }}
            >
              <div className="flex flex-col" style={{ gap: "0.375rem" }}>
                <span
                  className="mono dim"
                  style={{
                    fontSize: "0.65625rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  }}
                >
                  {isServerList ? tAccess("header.kicker") : t("header.kicker")}
                </span>
                <h1
                  className="text-fg-0"
                  style={{
                    margin: 0,
                    fontSize: "1.75rem",
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                  }}
                >
                  {t("header.title")}
                </h1>
                <p
                  className="dim"
                  style={{
                    margin: 0,
                    fontSize: "0.8125rem",
                    maxWidth: "38.75rem",
                  }}
                >
                  {isServerList
                    ? tAccess("header.subtitle")
                    : t("header.subtitle")}
                </p>
              </div>
              <div
                className="welcome-actions flex items-center shrink-0"
                style={{ gap: "0.5rem" }}
              >
                {canConnectFolder && (
                  <button
                    type="button"
                    className="btn"
                    onClick={handleConnectFolder}
                  >
                    <Upload size="0.8125rem" />
                    {t("header.openFolder")}
                  </button>
                )}
                {isServerList && (
                  <button
                    type="button"
                    className="btn"
                    onClick={handleImportArchive}
                  >
                    <FileArchive size="0.8125rem" />
                    {tImport("open")}
                  </button>
                )}
                {!isServerList && (
                  <button
                    type="button"
                    className="btn"
                    onClick={handleCloneFromGit}
                  >
                    <GitBranch size="0.8125rem" />
                    {t("header.cloneFromGit")}
                  </button>
                )}
                {!isServerList && canConnectServer && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => {
                      void navigate(CONNECT_SERVER_PATH);
                    }}
                    data-testid="welcome-connect-server"
                  >
                    <Server size="0.8125rem" />
                    {tLocal("welcome.connect")}
                  </button>
                )}
                <button
                  type="button"
                  className="btn primary lg"
                  data-tour="home-new-project"
                  onClick={handleCreateProject}
                >
                  <Plus size="0.875rem" />
                  {t("header.newProject")}
                </button>
              </div>
            </div>

            <div
              className="welcome-toolbar flex items-center"
              style={{ gap: "0.75rem", flexWrap: "wrap" }}
            >
              <div
                className="welcome-search flex items-center flex-1"
                data-tour="home-search"
                style={{
                  gap: "0.5rem",
                  minWidth: "13.75rem",
                  background: "var(--bg-1)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-2)",
                  padding: "0.375rem 0.75rem",
                }}
              >
                <Search
                  size="0.8125rem"
                  style={{ color: "var(--fg-3)", flexShrink: 0 }}
                />
                <input
                  ref={searchRef}
                  type="text"
                  className="input"
                  style={{
                    background: "transparent",
                    border: 0,
                    padding: 0,
                    fontSize: "0.8125rem",
                    flex: 1,
                    minWidth: 0,
                    outline: "none",
                  }}
                  placeholder={t("filters.search")}
                  aria-label={t("filters.search")}
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                  }}
                  onKeyDown={(e) => {
                    // Escape только снимает фокус: стирать набранное —
                    // отнимать у человека уже сделанную работу.
                    if (e.key === "Escape") e.currentTarget.blur();
                  }}
                />
                {!isPhone && (
                  <span className="kbd" title={t("filters.searchHint")}>
                    /
                  </span>
                )}
              </div>
              {isPhone ? (
                <FilterSheet
                  activeCount={
                    (filter !== "active" ? 1 : 0) +
                    (showScopeFilter && scope !== "all" ? 1 : 0) +
                    (sort !== "recent" ? 1 : 0)
                  }
                  onReset={() => {
                    setFilter("active");
                    setScope("all");
                    handleChangeSort("recent");
                  }}
                  testId="welcome-filters"
                >
                  {filterGroups}
                </FilterSheet>
              ) : (
                filterGroups
              )}
            </div>

            {isRecentStripVisible && (
              <div style={{ marginBottom: "1.375rem" }}>
                <div
                  className="flex items-center"
                  style={{ gap: "0.375rem", marginBottom: "0.625rem" }}
                >
                  <History size="0.6875rem" style={{ color: "var(--fg-3)" }} />
                  <h2
                    className="mono dim m-0"
                    style={{
                      fontSize: "0.65625rem",
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                    }}
                  >
                    {t("recent.title")}
                  </h2>
                </div>
                <div
                  className="flex items-stretch"
                  style={{ gap: "0.625rem", flexWrap: "wrap" }}
                >
                  {recentProjects.map((project) => (
                    <RecentProjectTile
                      key={project.id}
                      project={project}
                      onOpen={() => {
                        handleOpenProject(project);
                      }}
                    />
                  ))}
                </div>
              </div>
            )}

            {showCloud && (
              <CloudNotices
                view={cloudView}
                failed={cloud.isError}
                retrying={cloud.isFetching}
                onRetry={() => {
                  void cloud.refetch();
                }}
                onReconnect={(server) => {
                  void navigate(connectServerPath({ server, projectId: null }));
                }}
              />
            )}

            {isLoading ? (
              <div className="flex justify-center py-16">
                <Spinner />
              </div>
            ) : isError && !projects ? (
              <LoadError
                retrying={isFetching}
                onRetry={() => {
                  void refetch();
                }}
              />
            ) : filtered.length === 0 && cloudVisible.length === 0 ? (
              <EmptyState
                onCreate={handleCreateProject}
                onClone={isServerList ? undefined : handleCloneFromGit}
                onImport={isServerList ? handleImportArchive : undefined}
                query={query}
                onResetQuery={handleResetQuery}
                variant={isServerList ? "server" : "local"}
                scopeFiltered={showScopeFilter && scope !== "all"}
                onResetScope={() => {
                  setScope("all");
                }}
                onLocalStudio={handleLocalStudio}
              />
            ) : (
              <div
                ref={gridRef}
                onKeyDown={handleGridKeyDown}
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fill, minmax(min(22.5rem, 100%), 1fr))",
                  gap: "1rem",
                }}
              >
                {filtered.map((project) => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    onOpen={() => {
                      handleOpenProject(project);
                    }}
                    onTogglePin={() => {
                      handleTogglePin(project);
                    }}
                    onToggleArchive={() => {
                      handleToggleArchive(project);
                    }}
                    cloudHost={
                      cloudView.linked.get(project.id.toLowerCase())?.host
                    }
                  />
                ))}
                {cloudVisible.map((entry) => (
                  <CloudProjectCard
                    key={`${entry.server.credential_id}:${entry.project.id}`}
                    entry={entry}
                    onOpen={() => {
                      setOpening(entry);
                    }}
                  />
                ))}
                <NewProjectCard onClick={handleCreateProject} />
              </div>
            )}

            {/* Лента строится из локальных логов сборки: на сервере её нет. */}
            {!lacks("local_services_ui") && <RecentActivity />}
          </div>
        </div>

        {systemChatOpen && <ChatDock onClose={toggleSystemChat} />}
      </div>

      <AppStatusBar />
      {showCloud && (
        <CloudOpenDialog
          entry={opening}
          onClose={() => {
            setOpening(null);
          }}
          onOpened={(id) => {
            setOpening(null);
            void navigate(`/projects/${id}`);
          }}
          onReconnect={(server) => {
            setOpening(null);
            void navigate(connectServerPath({ server, projectId: null }));
          }}
        />
      )}
      {isServerList && (
        <ProjectImportDialog
          isOpen={importOpen}
          onClose={() => {
            setImportOpen(false);
          }}
        />
      )}
    </div>
  );
};
