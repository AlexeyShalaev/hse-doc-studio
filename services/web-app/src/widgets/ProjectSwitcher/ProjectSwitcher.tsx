import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Command } from "cmdk";
import { ChevronDown, FolderPlus, GraduationCap, Plus } from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { useKindMeta, useProjects, useTemplateMeta } from "@entities/project";
import { useRecentProjectIds } from "@shared/lib";

type Project = z.infer<typeof ProjectResponseSchema>;

/** Стор хранит до 12 визитов, но в поповере длинный хвост только мешает. */
const RECENT_GROUP_LIMIT = 8;
const PANEL_MIN_WIDTH = 380;
const PANEL_VIEWPORT_MARGIN = 8;
const PANEL_OFFSET = 6;

type PanelRect = {
  left: number;
  top: number;
  width: number;
};

// Заголовки групп cmdk рендерятся в [cmdk-group-heading] без своих стилей —
// в index.css правила для них нет, поэтому передаём готовый узел со стилями.
const GROUP_HEADING_STYLE: CSSProperties = {
  display: "block",
  padding: "6px 8px 4px",
  fontFamily: "var(--font-mono)",
  fontSize: 9.5,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
  color: "var(--fg-3)",
};

type ProjectSwitcherRowProps = {
  project: Project;
  isCurrent: boolean;
  onSelectProject: (projectId: string) => void;
};

const ProjectSwitcherRow = ({
  project,
  isCurrent,
  onSelectProject,
}: ProjectSwitcherRowProps) => {
  const templateMeta = useTemplateMeta(project);
  const TemplateIcon = templateMeta.icon;
  const kindMeta = useKindMeta(project.kind);
  const KindIcon = kindMeta.icon;
  const kindColor = `oklch(58% ${String(kindMeta.chroma)} ${String(kindMeta.hue)})`;

  return (
    <Command.Item
      className="combo-item"
      // cmdk фильтрует по value, а не по разметке: путь к папке обязан быть в
      // строке поиска — проекты часто ищут «который лежал в ~/vkr», а не по имени.
      // id добавлен, чтобы одноимённые проекты не схлопнулись в один пункт.
      value={`${project.name} ${project.folder} ${project.id}`}
      onSelect={() => {
        onSelectProject(project.id);
      }}
    >
      <TemplateIcon
        size={14}
        style={{
          flexShrink: 0,
          color: isCurrent ? "var(--accent)" : "var(--fg-2)",
        }}
      />
      <span
        className="truncate"
        style={{
          color: "var(--fg-0)",
          flex: "0 1 auto",
          minWidth: 0,
          fontWeight: isCurrent ? 600 : 400,
        }}
      >
        {project.name}
      </span>
      <span
        className="mono truncate"
        style={{
          flex: "1 1 auto",
          minWidth: 0,
          fontSize: 10.5,
          color: "var(--fg-3)",
        }}
      >
        {project.folder}
      </span>
      <span
        className="chip"
        style={{
          flexShrink: 0,
          background: "transparent",
          color: kindColor,
          borderColor: `color-mix(in oklch, ${kindColor} 30%, transparent)`,
        }}
      >
        <KindIcon size={10} />
        {kindMeta.label}
      </span>
    </Command.Item>
  );
};

export type ProjectSwitcherProps = {
  /** Проект, открытый прямо сейчас: подсвечивается в списке и в триггере. */
  currentProjectId?: string | undefined;
  /** Передан → компонент управляемый (для ⌘P снаружи). Опущен → сам с собой. */
  isOpen?: boolean | undefined;
  /** Дёргается в обоих режимах: и когда открывают, и когда закрывают. */
  onOpenChange?: ((isOpen: boolean) => void) | undefined;
};

/**
 * Преемник борта проектов: кнопка в титулбаре + cmdk-поповер со списком
 * «Недавние → Закреплённые → Все». Проект попадает ровно в одну группу.
 *
 * Открытость работает в двух режимах: без пропа `isOpen` компонент держит
 * состояние сам (клик по триггеру), с пропом — становится управляемым, чтобы
 * глобальный ⌘P мог открыть его снаружи.
 */
export const ProjectSwitcher = ({
  currentProjectId,
  isOpen,
  onOpenChange,
}: ProjectSwitcherProps) => {
  const { t, i18n } = useTranslation("appChrome");
  const navigate = useNavigate();
  const { data } = useProjects();
  const recentIds = useRecentProjectIds();

  const [isOpenInternal, setIsOpenInternal] = useState(false);
  const [rect, setRect] = useState<PanelRect | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const isControlled = isOpen !== undefined;
  const isPanelOpen = isControlled ? isOpen : isOpenInternal;

  const setPanelOpen = useCallback(
    (next: boolean) => {
      if (!isControlled) setIsOpenInternal(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  const visibleProjects = useMemo(
    () => (data ?? []).filter((project) => !project.archived),
    [data],
  );

  const currentProject = useMemo(
    () =>
      currentProjectId === undefined
        ? undefined
        : (data ?? []).find((project) => project.id === currentProjectId),
    [currentProjectId, data],
  );

  const collator = useMemo(
    () => new Intl.Collator(i18n.language),
    [i18n.language],
  );

  const recentProjects = useMemo(() => {
    const byId = new Map(
      visibleProjects.map((project) => [project.id, project] as const),
    );
    const picked: Project[] = [];
    for (const id of recentIds) {
      // Запись в persist может пережить удаление или архивацию проекта.
      const project = byId.get(id);
      if (!project) continue;
      picked.push(project);
      if (picked.length === RECENT_GROUP_LIMIT) break;
    }
    return picked;
  }, [recentIds, visibleProjects]);

  const pinnedProjects = useMemo(() => {
    const inRecent = new Set(recentProjects.map((project) => project.id));
    return visibleProjects
      .filter((project) => project.pinned && !inRecent.has(project.id))
      .sort((a, b) => collator.compare(a.name, b.name));
  }, [collator, recentProjects, visibleProjects]);

  const otherProjects = useMemo(() => {
    const shown = new Set([
      ...recentProjects.map((project) => project.id),
      ...pinnedProjects.map((project) => project.id),
    ]);
    return visibleProjects
      .filter((project) => !shown.has(project.id))
      .sort((a, b) => collator.compare(a.name, b.name));
  }, [collator, pinnedProjects, recentProjects, visibleProjects]);

  const triggerMeta = useTemplateMeta(currentProject);
  const TriggerIcon = triggerMeta.icon;

  const place = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = Math.max(r.width, PANEL_MIN_WIDTH);
    // Триггер живёт в титулбаре у левого края, но панель шире его — держим её
    // в пределах вьюпорта, иначе на узком экране список уедет за правый край.
    const maxLeft = Math.max(
      PANEL_VIEWPORT_MARGIN,
      window.innerWidth - width - PANEL_VIEWPORT_MARGIN,
    );
    setRect({
      left: Math.min(Math.max(r.left, PANEL_VIEWPORT_MARGIN), maxLeft),
      top: r.bottom + PANEL_OFFSET,
      width: Math.min(width, window.innerWidth - PANEL_VIEWPORT_MARGIN * 2),
    });
  }, []);

  useLayoutEffect(() => {
    if (isPanelOpen) place();
  }, [isPanelOpen, place]);

  useEffect(() => {
    if (!isPanelOpen) return undefined;
    const handleReposition = () => {
      place();
    };
    const handlePointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        panelRef.current?.contains(target)
      )
        return;
      setPanelOpen(false);
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setPanelOpen(false);
      triggerRef.current?.focus();
    };
    window.addEventListener("resize", handleReposition);
    window.addEventListener("scroll", handleReposition, true);
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("resize", handleReposition);
      window.removeEventListener("scroll", handleReposition, true);
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isPanelOpen, place, setPanelOpen]);

  const handleGo = useCallback(
    (to: string) => {
      setPanelOpen(false);
      void navigate(to);
    },
    [navigate, setPanelOpen],
  );

  const handleSelectProject = useCallback(
    (projectId: string) => {
      // Ведём на /projects/<id>, а не сразу в документ: редирект сам вернёт
      // пользователя на последний открытый в этом проекте документ.
      handleGo(`/projects/${projectId}`);
    },
    [handleGo],
  );

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="row-btn tt shrink-0"
        data-tt={t("projectSwitcher.triggerHint")}
        aria-label={t("projectSwitcher.trigger")}
        aria-haspopup="dialog"
        aria-expanded={isPanelOpen}
        style={{ width: "auto", padding: "4px 8px", maxWidth: 320 }}
        onClick={() => {
          setPanelOpen(!isPanelOpen);
        }}
      >
        <TriggerIcon
          size={14}
          style={{ flexShrink: 0, color: "var(--fg-2)" }}
        />
        <span
          className="truncate"
          style={{ minWidth: 0, color: "var(--fg-0)", fontWeight: 500 }}
        >
          {currentProject
            ? currentProject.name
            : t("projectSwitcher.noProject")}
        </span>
        <ChevronDown
          size={12}
          style={{ flexShrink: 0, color: "var(--fg-3)" }}
        />
      </button>

      {isPanelOpen &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="combo-menu"
            style={{
              position: "fixed",
              left: rect.left,
              top: rect.top,
              width: rect.width,
              zIndex: 200,
            }}
          >
            <Command loop label={t("projectSwitcher.trigger")}>
              <Command.Input
                className="combo-input"
                placeholder={t("projectSwitcher.search")}
                autoFocus
              />
              <Command.List className="combo-list">
                <Command.Empty className="combo-empty">
                  {t("projectSwitcher.empty")}
                </Command.Empty>

                {recentProjects.length > 0 && (
                  <Command.Group
                    heading={
                      <span style={GROUP_HEADING_STYLE}>
                        {t("projectSwitcher.recent")}
                      </span>
                    }
                  >
                    {recentProjects.map((project) => (
                      <ProjectSwitcherRow
                        key={project.id}
                        project={project}
                        isCurrent={project.id === currentProjectId}
                        onSelectProject={handleSelectProject}
                      />
                    ))}
                  </Command.Group>
                )}

                {pinnedProjects.length > 0 && (
                  <Command.Group
                    heading={
                      <span style={GROUP_HEADING_STYLE}>
                        {t("projectSwitcher.pinned")}
                      </span>
                    }
                  >
                    {pinnedProjects.map((project) => (
                      <ProjectSwitcherRow
                        key={project.id}
                        project={project}
                        isCurrent={project.id === currentProjectId}
                        onSelectProject={handleSelectProject}
                      />
                    ))}
                  </Command.Group>
                )}

                {otherProjects.length > 0 && (
                  <Command.Group
                    heading={
                      <span style={GROUP_HEADING_STYLE}>
                        {t("projectSwitcher.all")}
                      </span>
                    }
                  >
                    {otherProjects.map((project) => (
                      <ProjectSwitcherRow
                        key={project.id}
                        project={project}
                        isCurrent={project.id === currentProjectId}
                        onSelectProject={handleSelectProject}
                      />
                    ))}
                  </Command.Group>
                )}
              </Command.List>
            </Command>

            <div
              style={{
                borderTop: "1px solid var(--border)",
                padding: 4,
                display: "flex",
                flexDirection: "column",
                gap: 2,
              }}
            >
              <button
                type="button"
                className="row-btn"
                onClick={() => {
                  handleGo("/");
                }}
              >
                <GraduationCap size={14} style={{ color: "var(--fg-2)" }} />
                <span style={{ flex: 1 }}>
                  {t("projectSwitcher.allProjects")}
                </span>
              </button>
              <button
                type="button"
                className="row-btn"
                onClick={() => {
                  handleGo("/wizard?mode=create");
                }}
              >
                <Plus size={14} style={{ color: "var(--fg-2)" }} />
                <span style={{ flex: 1 }}>
                  {t("projectSwitcher.newProject")}
                </span>
                <span className="kbd">⌘N</span>
              </button>
              <button
                type="button"
                className="row-btn"
                onClick={() => {
                  handleGo("/wizard?mode=connect");
                }}
              >
                <FolderPlus size={14} style={{ color: "var(--fg-2)" }} />
                <span style={{ flex: 1 }}>
                  {t("projectSwitcher.connectFolder")}
                </span>
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
};
