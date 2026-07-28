import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { History, Plus, Search, Upload } from "lucide-react";
import { clsx } from "clsx";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import {
  useProjects,
  useTemplateMeta,
  useUpdateProject,
} from "@entities/project";
import { useRecentProjectIds, useWorkspaceStore } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { ChatDock } from "@widgets/ChatDock";
import { EmptyState } from "./EmptyState";
import { NewProjectCard } from "./NewProjectCard";
import { ProjectCard } from "./ProjectCard";
import { RecentActivity } from "./RecentActivity";

type FilterType = "active" | "all" | "archived";
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
        gap: 10,
        padding: "9px 12px",
        flex: "1 1 210px",
        maxWidth: 300,
        minWidth: 0,
      }}
    >
      <span
        className="flex items-center justify-center shrink-0"
        style={{
          width: 26,
          height: 26,
          borderRadius: 7,
          background: `oklch(60% 0.16 ${hue} / 0.14)`,
          color: `oklch(70% 0.16 ${hue})`,
        }}
      >
        <Icon size={13} />
      </span>
      {/* minWidth инлайном: утилита min-w-0 в этой сборке Tailwind не рождается. */}
      <span className="flex flex-col" style={{ minWidth: 0, gap: 1 }}>
        <span
          className="truncate text-fg-0"
          style={{ fontSize: 12.5, fontWeight: 500 }}
        >
          {project.name}
        </span>
        <span
          className="mono truncate"
          style={{ fontSize: 10, color: "var(--fg-3)" }}
        >
          {project.folder}
        </span>
      </span>
    </button>
  );
};

export const WelcomePage = () => {
  const { t, i18n } = useTranslation("welcome");
  const navigate = useNavigate();
  const { data: projects, isLoading } = useProjects();
  const { mutate: updateProject } = useUpdateProject();
  const recentIds = useRecentProjectIds();
  // The one unified agent, docked between the title and status bars (same
  // panel as in a project — here it has no project bound, so app/system tools).
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterType>("active");
  const [sort, setSort] = useState<SortMode>(readStoredSortMode);

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

    if (query.trim()) {
      const ql = query.trim().toLowerCase();
      xs = xs.filter(
        (p) =>
          p.name.toLowerCase().includes(ql) ||
          p.folder.toLowerCase().includes(ql) ||
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
  }, [projects, filter, query, sort, collator, recentRank]);

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

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div
            style={{
              maxWidth: 1180,
              margin: "0 auto",
              padding: "36px 32px 80px",
            }}
          >
            <div
              className="flex items-center justify-between"
              style={{ marginBottom: 32 }}
            >
              <div className="flex flex-col" style={{ gap: 6 }}>
                <span
                  className="mono dim"
                  style={{
                    fontSize: 10.5,
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  }}
                >
                  {t("header.kicker")}
                </span>
                <h1
                  className="text-fg-0"
                  style={{
                    margin: 0,
                    fontSize: 28,
                    fontWeight: 600,
                    letterSpacing: "-0.02em",
                  }}
                >
                  {t("header.title")}
                </h1>
                <p
                  className="dim"
                  style={{ margin: 0, fontSize: 13, maxWidth: 620 }}
                >
                  {t("header.subtitle")}
                </p>
              </div>
              <div className="flex items-center shrink-0" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn"
                  onClick={handleConnectFolder}
                >
                  <Upload size={13} />
                  {t("header.openFolder")}
                </button>
                <button
                  type="button"
                  className="btn primary lg"
                  onClick={handleCreateProject}
                >
                  <Plus size={14} />
                  {t("header.newProject")}
                </button>
              </div>
            </div>

            <div
              className="flex items-center"
              style={{ marginBottom: 18, gap: 12, flexWrap: "wrap" }}
            >
              <div
                className="flex items-center flex-1"
                style={{
                  gap: 8,
                  minWidth: 220,
                  background: "var(--bg-1)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--r-2)",
                  padding: "6px 12px",
                }}
              >
                <Search
                  size={13}
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
                    fontSize: 13,
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
                <span className="kbd" title={t("filters.searchHint")}>
                  /
                </span>
              </div>
              <div
                className="seg shrink-0"
                role="group"
                aria-label={t("filters.label")}
              >
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
              <div
                className="seg shrink-0"
                role="group"
                aria-label={t("sort.label")}
              >
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
            </div>

            {isRecentStripVisible && (
              <div style={{ marginBottom: 22 }}>
                <div
                  className="flex items-center"
                  style={{ gap: 6, marginBottom: 10 }}
                >
                  <History size={11} style={{ color: "var(--fg-3)" }} />
                  <h2
                    className="mono dim m-0"
                    style={{
                      fontSize: 10.5,
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                    }}
                  >
                    {t("recent.title")}
                  </h2>
                </div>
                <div
                  className="flex items-stretch"
                  style={{ gap: 10, flexWrap: "wrap" }}
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

            {isLoading ? (
              <div className="flex justify-center py-16">
                <Spinner />
              </div>
            ) : filtered.length === 0 ? (
              <EmptyState
                onCreate={handleCreateProject}
                query={query}
                onResetQuery={handleResetQuery}
              />
            ) : (
              <div
                ref={gridRef}
                onKeyDown={handleGridKeyDown}
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
                  gap: 16,
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
                  />
                ))}
                <NewProjectCard onClick={handleCreateProject} />
              </div>
            )}

            <RecentActivity />
          </div>
        </div>

        {systemChatOpen && <ChatDock onClose={toggleSystemChat} />}
      </div>

      <AppStatusBar />
    </div>
  );
};
