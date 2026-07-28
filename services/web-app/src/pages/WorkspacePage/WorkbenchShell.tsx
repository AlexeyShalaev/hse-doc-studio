import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";

import { useDocuments } from "@entities/document";
import { useCompileStreamStore } from "@entities/compile";
import { useVcsStatus } from "@entities/vcs";
import { ActivityBar } from "@widgets/ActivityBar";
import { DocumentsPanel } from "@widgets/DocumentsPanel";
import { ReviewPanel } from "@widgets/ReviewPanel";
import { SubmitPanel } from "@widgets/SubmitPanel";
import { ChatDock } from "@widgets/ChatDock";
import type { WorkbenchActivity } from "@shared/lib";
import { getLastDoc, usePaneResize, useWorkspaceStore } from "@shared/lib";
import { ResizeHandle } from "@shared/ui";
import { useCheckpointReadiness } from "./lib";
import { FilesPanel } from "./panels";
// Прямым путём, а не через ./panels: бочку panels/index.ts сводит интегратор.
import { ProjectSettingsPanel } from "./panels/ProjectSettingsPanel";

const PANEL_WIDTH_STORAGE_KEY = "hse-studio.workbench.panelWidth";

const PANEL_WIDTH = { default: 260, min: 240, max: 380 };

export type WorkbenchShellProps = {
  projectId: string;
  /** Активный документ; для канвасов инструментов — пустая строка. */
  selectedDocId: string;
  isProjectSettingsActive: boolean;
  isVersionsActive: boolean;
  onSelectDoc: (docId: string, tab?: string) => void;
  /** Активная секция настроек проекта — её подсвечивает оглавление в панели. */
  /** Сырой параметр маршрута настроек — разбирает панель. */
  projectSettingsSection: string;
  /** Активный блок «Метаданных»; выбирается и в оглавлении, и в карточке. */
  /** Центральный канвас — его выбирает маршрут в WorkspacePage. */
  canvas: React.ReactNode;
};

/**
 * Что показывает сменная панель. «settings» — не режим верстака: он не
 * запоминается между сессиями и не подсвечивается в рейке, поэтому в
 * WorkbenchActivity его нет и быть не должно.
 */
type PanelMode = WorkbenchActivity | "settings";

/**
 * Каркас рабочей области: рейка режимов, ОДНА сменная панель, центральная
 * колонка с канвасом и пристыкованный агент.
 *
 * Инвариант раскладки: ChatDock обязан остаться ПРЯМЫМ flex-ребёнком
 * .workbench-body — у него `display: contents`, и его собственные дети
 * (ручка размера и панель) раскладываются этим флексом. Любая обёртка вокруг
 * ChatDock ломает ширину агента.
 */
export const WorkbenchShell = ({
  projectId,
  selectedDocId,
  isProjectSettingsActive,
  isVersionsActive,
  onSelectDoc,
  projectSettingsSection,
  canvas,
}: WorkbenchShellProps) => {
  const { t } = useTranslation("workbench");
  const navigate = useNavigate();

  const activity = useWorkspaceStore((state) => state.activity);
  const setActivity = useWorkspaceStore((state) => state.setActivity);
  const sidebarCollapsed = useWorkspaceStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useWorkspaceStore(
    (state) => state.setSidebarCollapsed,
  );
  const toggleSidebar = useWorkspaceStore((state) => state.toggleSidebar);
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);

  const [isMobilePanelOpen, setIsMobilePanelOpen] = useState(false);
  // Что показывает панель, вместе с входами, при которых это решено. Правка
  // состояния прямо в рендере (а не эффектом) — документированный приём React
  // для «подстройки под изменившийся проп»: эффект с setState здесь дал бы
  // лишний каскадный рендер на каждом переходе.
  const [panelState, setPanelState] = useState<{
    isSettings: boolean;
    activity: WorkbenchActivity;
    mode: PanelMode;
  }>(() => ({
    isSettings: isProjectSettingsActive,
    activity,
    mode: isProjectSettingsActive ? "settings" : activity,
  }));

  if (
    panelState.isSettings !== isProjectSettingsActive ||
    panelState.activity !== activity
  ) {
    setPanelState({
      isSettings: isProjectSettingsActive,
      activity,
      // Открылся канвас настроек, а режим не трогали → показываем оглавление.
      // Сменился режим (рейка, шорткат) → панель этого режима, даже если
      // настройки всё ещё открыты: рейка меняет панель, а не адрес.
      mode:
        isProjectSettingsActive && panelState.activity === activity
          ? "settings"
          : activity,
    });
  }

  const panelMode: PanelMode = panelState.mode;

  const panelResize = usePaneResize({
    storageKey: PANEL_WIDTH_STORAGE_KEY,
    defaultWidth: PANEL_WIDTH.default,
    minWidth: PANEL_WIDTH.min,
    maxWidth: PANEL_WIDTH.max,
    direction: 1,
  });

  const { data: documents } = useDocuments(projectId);
  const { data: vcsStatus } = useVcsStatus(projectId);
  const compileStreams = useCompileStreamStore((state) => state.streams);
  const checkpoints = useCheckpointReadiness(projectId);

  // Счётчики рейки считает оболочка — сама рейка ничего не загружает.
  const counts = useMemo(() => {
    const docs = documents ?? [];
    const errors = docs.reduce((sum, doc) => sum + (doc.errors ?? 0), 0);
    const warnings = docs.reduce((sum, doc) => sum + (doc.warnings ?? 0), 0);
    const prefix = `${projectId}::`;
    const isBuilding = Object.entries(compileStreams).some(
      ([key, stream]) => key.startsWith(prefix) && stream.status === "running",
    );
    const changedFiles = vcsStatus
      ? vcsStatus.modified + vcsStatus.untracked + vcsStatus.staged
      : 0;
    // Профиль без описанного состава (items == null) даёт isUnknown — бейджа
    // быть не должно, иначе рейка показывала бы уверенный ноль там, где на
    // самом деле нечего считать.
    const activeReadiness = checkpoints.activeReadiness;
    const submitBlockers =
      activeReadiness && !activeReadiness.isUnknown
        ? activeReadiness.blockers
        : 0;

    return { errors, warnings, isBuilding, submitBlockers, changedFiles };
  }, [
    checkpoints.activeReadiness,
    compileStreams,
    documents,
    projectId,
    vcsStatus,
  ]);

  /**
   * Куда ведёт режим, когда уходить приходится с полноэкранной страницы.
   * «Документы» и «Замечания» делят один канвас — документ, поэтому оба
   * возвращают туда, где пользователь остановился.
   */
  const activityCanvasPath = (next: WorkbenchActivity): string => {
    switch (next) {
      case "files":
        return "/files";
      case "submit":
        // Точку выберет сам экран сдачи — ближайшую или закреплённую.
        return "/submit";
      case "documents":
      case "review": {
        const lastDocId = getLastDoc(projectId);
        return lastDocId === null ? "/documents" : `/documents/${lastDocId}`;
      }
    }
  };

  // На узком экране рейка сама и есть навигация: тап по режиму выдвигает
  // панель, повторный тап по уже активному — прячет. Отдельная кнопка-гамбургер
  // была бы третьим способом сделать то же самое и налезала бы на рейку.
  const handleSelectActivity = (next: WorkbenchActivity): void => {
    if (next === activity && isMobilePanelOpen) {
      setIsMobilePanelOpen(false);
      return;
    }
    // Настройки проекта и история — полноэкранные страницы, не парные ни одному
    // режиму. Оставаться на них, переключив режим, нельзя: пользователь жмёт
    // «Документы», а перед ним по-прежнему настройки, и меняется только панель.
    // Поэтому с такой страницы рейка уводит в канвас самого режима.
    const isFullPageCanvas = isProjectSettingsActive || isVersionsActive;

    // Клик по УЖЕ активному режиму сворачивает панель, по любому другому —
    // всегда разворачивает. Без этого кнопка «Свернуть» в шапке панели делала
    // рейку мёртвой: подсветка активности переключалась, ширина панели
    // оставалась нулевой, и развернуть её можно было только незаметным ⌘B.
    // На полноэкранной странице сворачивать нечего — оттуда надо уходить.
    if (next === activity && !isFullPageCanvas && panelMode !== "settings") {
      toggleSidebar();
      return;
    }
    setSidebarCollapsed(false);
    setActivity(next);
    // Явно, а не подстройкой в рендере: клик по УЖЕ активному режиму ничего не
    // меняет во входах, но панель обязан забрать у настроек.
    setPanelState({
      // Намеренно текущее значение маршрута, а не false: маршрут ещё не
      // сменился, и false тут же вернулся бы синхронизацией в рендере, снова
      // показав панель настроек. Как только переход состоится, она сама
      // пересчитает состояние.
      isSettings: isProjectSettingsActive,
      activity: next,
      mode: next,
    });
    setIsMobilePanelOpen(true);
    if (isFullPageCanvas) goTo(activityCanvasPath(next));
  };

  const handleSelectDoc = (docId: string, tab?: string): void => {
    setIsMobilePanelOpen(false);
    onSelectDoc(docId, tab);
  };

  const goTo = (path: string): void => {
    setIsMobilePanelOpen(false);
    void navigate(`/projects/${projectId}${path}`);
  };

  useEffect(() => {
    if (!isMobilePanelOpen) return;
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setIsMobilePanelOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isMobilePanelOpen]);

  const panel = ((): React.ReactNode => {
    if (panelMode === "settings") {
      return (
        <ProjectSettingsPanel
          projectId={projectId}
          activeSection={projectSettingsSection}
          onSelectSection={(sectionId) => {
            goTo(`/project-settings/${sectionId}`);
          }}
        />
      );
    }
    switch (panelMode) {
      case "documents":
        return (
          <DocumentsPanel
            projectId={projectId}
            selectedDocId={selectedDocId}
            onSelectDoc={handleSelectDoc}
            onOpenForm={(formId) => {
              goTo(`/submit/form/${formId}`);
            }}
            activeFormIds={checkpoints.activeReadiness?.formIds}
          />
        );
      case "review":
        return (
          <ReviewPanel
            projectId={projectId}
            selectedDocId={selectedDocId}
            onSelectDoc={(docId) => {
              handleSelectDoc(docId, "checks");
            }}
          />
        );
      case "submit":
        return (
          <SubmitPanel
            projectId={projectId}
            selectedDocId={selectedDocId}
            onSelectDoc={handleSelectDoc}
            onOpenCheckpoint={(profileId) => {
              goTo(`/submit/cp/${profileId}`);
            }}
            onOpenForm={(formId) => {
              goTo(`/submit/form/${formId}`);
            }}
            onOpenSignatures={() => {
              goTo("/submit/signatures");
            }}
            onOpenRequirements={() => {
              goTo("/submit/requirements");
            }}
            readinessByProfile={checkpoints.readinessByProfile}
            activeFormIds={checkpoints.activeReadiness?.formIds}
            pinnedProfileId={checkpoints.pinnedProfileId}
            onPinProfile={checkpoints.setPinnedProfileId}
          />
        );
      case "files":
        return <FilesPanel projectId={projectId} />;
    }
  })();

  // У каждого режима рейки своя пара «панель + центр»: документы — навигация и
  // редактор, замечания — ошибки и редактор, сдача — точки и упаковка. У
  // «Истории» пары нет, она полноэкранная. Оставлять сбоку панель прошлого
  // режима нельзя: она показывала бы документы или замечания, к открытому
  // центру отношения не имеющие, и читалась бы как часть Истории.
  //
  // Именно скрытие на время, а не setSidebarCollapsed: свёрнутость — это
  // пользовательская настройка, и Истории не следует её перезаписывать. Уйдя
  // из неё, пользователь получит панель ровно в том виде, в каком оставил.
  const isPanelHidden = sidebarCollapsed || isVersionsActive;

  return (
    <div className="workbench-body">
      <ActivityBar
        activity={activity}
        onSelectActivity={handleSelectActivity}
        onOpenProjectSettings={() => {
          // Повторный клик по «Настройкам» возвращает оглавление, даже если
          // канвас уже открыт и пользователь успел уйти в другой режим панели.
          setPanelState({ isSettings: true, activity, mode: "settings" });
          setSidebarCollapsed(false);
          goTo("/project-settings");
        }}
        isProjectSettingsActive={isProjectSettingsActive}
        onOpenVersions={() => {
          goTo("/versions");
        }}
        isVersionsActive={isVersionsActive}
        counts={counts}
        isAgentActive={systemChatOpen}
        onToggleAgent={toggleSystemChat}
        onOpenSystemSettings={() => {
          void navigate("/settings");
        }}
      />

      <div
        className={clsx(
          "workbench-sidebar",
          isMobilePanelOpen && !isVersionsActive && "mobile-open",
        )}
        style={{
          width: isPanelHidden ? 0 : panelResize.width,
          transition: panelResize.isResizing
            ? "none"
            : "width 0.22s var(--ease)",
        }}
      >
        {panel}
      </div>

      {!isPanelHidden && (
        <ResizeHandle
          active={panelResize.isResizing}
          label={t("dock.resize")}
          onDoubleClick={panelResize.reset}
          onKeyNudge={panelResize.nudge}
          onPointerDown={panelResize.startResize}
        />
      )}

      {isMobilePanelOpen && !isVersionsActive && (
        <button
          type="button"
          className="workspace-mobile-backdrop"
          aria-label={t("panel.collapse")}
          onClick={() => {
            setIsMobilePanelOpen(false);
          }}
        />
      )}

      <div className="workbench-center">
        <main className="workbench-canvas">{canvas}</main>
      </div>

      {/* Пристыкованный агент — прямой ребёнок .workbench-body, см. инвариант
          в шапке файла. */}
      {systemChatOpen && (
        <ChatDock projectId={projectId} onClose={toggleSystemChat} />
      )}
    </div>
  );
};
