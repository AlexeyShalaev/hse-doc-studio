import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useDocuments } from "@entities/document";
import { useProject } from "@entities/project";
import { useResumeProjectStreams, useStartCompileAll } from "@entities/compile";
import { DocumentTabs } from "@widgets/DocumentTabs";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { ProjectSwitcher } from "@widgets/ProjectSwitcher";
import type { WorkbenchActivity } from "@shared/lib";
import {
  setLastDoc,
  useGlobalHotkeys,
  useRecentProjectsStore,
  useWorkspaceStore,
} from "@shared/lib";
import { WorkbenchShell } from "./WorkbenchShell";
import {
  CheckpointView,
  FileEditorView,
  FormView,
  OverviewView,
  SubmitEntry,
  ProjectSettingsView,
  RequirementsView,
  SignaturesView,
  VersionsView,
} from "./panels";
import { SHARED_META_BLOCK_KEY } from "./panels/project-settings";

/**
 * Канвасы инструментов, у которых есть «свой» режим панели.
 *
 * Открытие такого адреса напрямую (закладка, ссылка агента, история браузера)
 * обязано подтянуть соответствующую панель: иначе /files показывает редактор с
 * подсказкой «выберите файл в дереве слева», а слева всё ещё список документов.
 *
 * Документ и обзор сюда НЕ входят намеренно: переход к документу из панели
 * «Замечания» не должен выкидывать пользователя обратно в «Документы».
 */
const CANVAS_ACTIVITY: Partial<Record<WorkspaceCanvas, WorkbenchActivity>> = {
  files: "files",
  "submit-pack": "submit",
  "submit-checkpoint": "submit",
  "submit-signatures": "submit",
  "submit-requirements": "submit",
  "submit-form": "submit",
};

/** Что показывает центральный канвас. Задаётся маршрутом, не рейкой. */
export type WorkspaceCanvas =
  | "overview"
  | "document"
  | "files"
  | "versions"
  | "project-settings"
  | "submit-pack"
  | "submit-signatures"
  | "submit-requirements"
  | "submit-form"
  | "submit-checkpoint";

export type WorkspacePageProps = {
  canvas: WorkspaceCanvas;
};

export const WorkspacePage = ({ canvas }: WorkspacePageProps) => {
  const {
    projectId = "",
    docId = "",
    formId = "",
    profileId = "",
    section = "",
  } = useParams<{
    projectId: string;
    docId: string;
    formId: string;
    profileId: string;
    section: string;
  }>();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId);
  const touchProject = useRecentProjectsStore((state) => state.touchProject);
  const setActivity = useWorkspaceStore((state) => state.setActivity);
  const toggleSidebar = useWorkspaceStore((state) => state.toggleSidebar);
  const { data: documents } = useDocuments(projectId);
  const { startAll } = useStartCompileAll(projectId);
  const [isSwitcherOpen, setIsSwitcherOpen] = useState(false);
  // Блок «Метаданных» выбирают в двух местах — в оглавлении (сменная панель) и
  // в самой карточке, — а общий предок у них только страница. Владельцем
  // черновика это НЕ делает: правки по-прежнему держит ProjectSettingsView, и
  // он же лечит устаревший слаг (автора разведут — блок вернётся к общему).
  const [metaBlock, setMetaBlock] = useState<string>(SHARED_META_BLOCK_KEY);

  // Параметр маршрута передаём как есть: и вид, и панель разбирают его сами
  // через resolveProjectSettingsGroup, который принимает id группы, id раздела
  // и мусор (последний превращается в группу по умолчанию). Разбирать здесь
  // нельзя — доступность групп зависит от каталога версии, который грузится
  // ниже по дереву.
  const projectSettingsSection = section;

  // Re-attach SSE streams for any in-progress build after page reload / new
  // tab. Must stay at the top level, outside any conditional render: inside a
  // panel it would unmount on every mode switch and silently drop the
  // project-wide "is building" lock.
  useResumeProjectStreams(projectId);

  // Свежесть проекта пишем только при реальном открытии рабочей области —
  // не при отрисовке списка проектов, иначе порядок «недавних» перетасует
  // сам заход на «/».
  useEffect(() => {
    if (!projectId) return;
    touchProject(projectId);
  }, [projectId, touchProject]);

  // Возврат в контекст: помним последний открытый документ проекта. Пишем из
  // маршрута (а не из обработчика клика), чтобы перезагрузка страницы тоже
  // обновляла память — и любой переход, минуя панель, тоже учитывался.
  useEffect(() => {
    if (!projectId || !docId) return;
    setLastDoc(projectId, docId);
  }, [projectId, docId]);

  // Панель следует за канвасом инструмента — но только при СМЕНЕ канваса, а не
  // на каждый рендер: иначе клик по «Документы» в рейке, пока открыт /files,
  // тут же отматывался бы обратно.
  useEffect(() => {
    const next = CANVAS_ACTIVITY[canvas];
    if (next) setActivity(next);
  }, [canvas, setActivity]);

  // Переход к документу может сразу открыть нужный вид центра. Панель
  // «Замечания» этим пользуется: клик по документу с ошибками должен вести к
  // самим замечаниям, а не к превью, из которого до них ещё два клика.
  const handleSelectDoc = (id: string, tab?: string): void => {
    const suffix = tab ? `?tab=${tab}` : "";
    void navigate(`/projects/${projectId}/documents/${id}${suffix}`);
  };

  // Шорткаты рабочей области. ⌘K / ⌘N / ⌘, сюда НЕ подключены намеренно: их
  // уже слушает CommandPalette, и вторая привязка того же сочетания открывала
  // бы палитру и тут же закрывала.
  useGlobalHotkeys({
    onToggleSidebar: toggleSidebar,
    onOpenIssues: () => {
      setActivity("review");
    },
    onSelectDocuments: () => {
      setActivity("documents");
    },
    onSelectFiles: () => {
      setActivity("files");
    },
    onSelectSubmit: () => {
      setActivity("submit");
    },
    onBuildAll: () => {
      startAll((documents ?? []).map((doc) => doc.id));
    },
    onOpenProjectSwitcher: () => {
      setIsSwitcherOpen(true);
    },
  });

  const canvasNode = ((): React.ReactNode => {
    if (!project) return null;
    switch (canvas) {
      case "document":
        return docId ? (
          <DocumentTabs projectId={projectId} docId={docId} />
        ) : null;
      case "files":
        return <FileEditorView projectId={projectId} />;
      case "versions":
        return <VersionsView project={project} />;
      case "project-settings":
        // key — по проекту и только по нему: пересборка на смене секции убила
        // бы отложенное сохранение вместе с недописанной правкой.
        return (
          <ProjectSettingsView
            key={project.id}
            project={project}
            section={projectSettingsSection}
            metaBlock={metaBlock}
            onSelectMetaBlock={setMetaBlock}
          />
        );
      case "submit-pack":
        return <SubmitEntry project={project} />;
      case "submit-checkpoint":
        return profileId ? (
          <CheckpointView project={project} profileId={profileId} />
        ) : (
          <SubmitEntry project={project} />
        );
      case "submit-signatures":
        return <SignaturesView project={project} />;
      case "submit-requirements":
        return <RequirementsView />;
      case "submit-form":
        return formId ? <FormView project={project} formId={formId} /> : null;
      case "overview":
        return (
          <OverviewView projectId={projectId} onSelectDoc={handleSelectDoc} />
        );
    }
  })();

  const projectIsNda = project?.meta?.nda === true;

  return (
    <div
      className="workspace-page flex flex-col flex-1 bg-bg-0"
      style={{ minHeight: 0 }}
    >
      <AppTitlebar
        projectName={project?.name ?? null}
        projectIsNda={projectIsNda}
        projectSwitcher={
          <ProjectSwitcher
            currentProjectId={projectId}
            isOpen={isSwitcherOpen}
            onOpenChange={setIsSwitcherOpen}
          />
        }
      />

      <WorkbenchShell
        projectId={projectId}
        selectedDocId={docId}
        isProjectSettingsActive={canvas === "project-settings"}
        isVersionsActive={canvas === "versions"}
        onSelectDoc={handleSelectDoc}
        projectSettingsSection={projectSettingsSection}
        canvas={canvasNode}
      />

      <AppStatusBar />
    </div>
  );
};
