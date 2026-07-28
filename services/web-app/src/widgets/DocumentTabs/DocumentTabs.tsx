import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Clock,
  Code,
  Columns2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileEdit,
  FileText,
  ListChecks,
  MoreHorizontal,
  PenTool,
  Play,
  RefreshCw,
  Terminal,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import {
  getDocMeta,
  getStatusMeta,
  isOfficeEditablePath,
  useCustomFileActions,
  useDocument,
} from "@entities/document";
import { useStartCompile } from "@entities/compile";
import { UploadCustomFileModal } from "@features/custom-document";
import { useProject } from "@entities/project";
import { EditorIcon, openInEditor, useEditors } from "@entities/system";
import { env } from "@shared/config";
import { Modal, Spinner } from "@shared/ui";
import { toast, useSyncTexStore } from "@shared/lib";
import {
  ChecksPane,
  CompilePane,
  DocSignaturesPane,
  HistoryPane,
  OfficeEditorPane,
  PreviewPane,
  SourcePane,
} from "./panes";

const customFileDownloadUrl = (projectId: string, relPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${relPath}`;

export type DocumentTabsProps = {
  projectId: string;
  docId: string;
};

/**
 * Что показывает центральная область документа.
 *
 * Проверки, сборка, журнал и подписи — такие же полноценные страницы центра,
 * как превью и редактор. Это осознанное отличие от VSCode: там в центре всегда
 * файл, поэтому всё остальное вытесняется в нижнюю панель, а у нас центр —
 * универсальный канвас, и «всё про документ» показывается прямо в нём.
 */
type DocView =
  | "preview"
  | "editor"
  | "side"
  | "checks"
  | "compile"
  | "history"
  | "signatures";

type ViewSegment = {
  id: DocView;
  label: string;
  icon: LucideIcon;
  title: string;
  isDisabled: boolean;
};

// Ниже этой ширины две колонки превращаются в две бесполезные щели: PDF
// перестаёт читаться, а редактор — набираться. Сегмент «Рядом» гаснет.
const SIDE_BY_SIDE_MIN_WIDTH = 720;

// ?tab= адресует вид центра. Значения сохранены прежними — на них ссылаются
// закладки, история браузера и сообщения агента.
const PAGE_VIEW_BY_PARAM: Record<string, DocView> = {
  checks: "checks",
  compile: "compile",
  history: "history",
  signatures: "signatures",
};

export const DocumentTabs = ({ projectId, docId }: DocumentTabsProps) => {
  const { t } = useTranslation("documents");
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");

  const setTabParam = (next: string | null) => {
    // Replace, not push — flipping views shouldn't bloat browser history.
    const params = new URLSearchParams(searchParams);
    if (next === null) {
      // Treat preview as the default — keep URLs clean.
      params.delete("tab");
    } else {
      params.set("tab", next);
    }
    setSearchParams(params, { replace: true });
  };

  const { data: project } = useProject(projectId);
  const { data: doc } = useDocument(projectId, docId);
  const { data: editorsData } = useEditors();
  const {
    start: handleBuild,
    isRunning,
    slot,
  } = useStartCompile(projectId, docId);
  const hasPriorBuild = slot !== undefined || doc?.last_compile_id != null;
  const { remove: removeCustomFile, isRemoving: isRevertingCustomFile } =
    useCustomFileActions(projectId, docId);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [revertConfirmOpen, setRevertConfirmOpen] = useState(false);

  // Единственный сегмент «Редактор» показывает либо исходник, либо офисный
  // редактор — что именно, решает формат артефакта: pptx-вариант презентации и
  // любая пользовательская загрузка в word/cell/slide открываются в ONLYOFFICE,
  // потому что CodeMirror их бинарь не откроет. Считаем до раннего выхода:
  // значение нужно эффектам SyncTeX.
  const isOfficeEditableArtifact = isOfficeEditablePath(doc?.output_file ?? "");
  const editorTabValue = isOfficeEditableArtifact ? "office" : "source";

  // Режим «Рядом» — состояние экрана, а не адреса: параметр ?tab= остаётся
  // памятью последнего одиночного режима, и переходы вроде «показать исходник»
  // (SyncTeX, клик по замечанию) не разваливают уже открытую пару панелей.
  const [isSplitRequested, setIsSplitRequested] = useState(false);
  const [paneEl, setPaneEl] = useState<HTMLDivElement | null>(null);
  const [paneWidth, setPaneWidth] = useState<number | null>(null);
  useEffect(() => {
    if (paneEl === null) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setPaneWidth(entry.contentRect.width);
    });
    observer.observe(paneEl);
    return () => {
      observer.disconnect();
    };
    // Пересоздаём наблюдателя, когда область появляется: до загрузки документа
    // её в DOM нет, и пустой массив зависимостей оставил бы её неизмеренной.
  }, [paneEl]);

  // До первого замера считаем, что места хватает: иначе сегмент моргнёт
  // заблокированным на первом кадре даже на широком экране.
  const canSplit = paneWidth === null || paneWidth >= SIDE_BY_SIDE_MIN_WIDTH;
  // Пара панелей — производное, а не хранимое состояние: когда места не стало,
  // экран молча возвращается к последнему одиночному режиму (его помнит ?tab=),
  // а когда место вернулось — к паре, без каскада перерисовок из эффекта.
  const isSideBySide = isSplitRequested && canSplit;

  const isEditorView = tabParam === "source" || tabParam === "office";
  const pageView = tabParam === null ? undefined : PAGE_VIEW_BY_PARAM[tabParam];
  // Страница (проверки/сборка/журнал) занимает центр целиком и старше «Рядом»:
  // делить экран между парой панелей и отдельной страницей нечего.
  const activeView: DocView = pageView
    ? pageView
    : isSideBySide
      ? "side"
      : isEditorView
        ? "editor"
        : "preview";

  // SyncTeX cross-pane jumps switch the view to the side being navigated to: a
  // forward jump (source→PDF) shows the preview; an inverse jump shows the
  // source. The target pane then consumes the pending jump from the store. В
  // режиме «Рядом» переключать нечего — обе панели уже на экране.
  const pdfJumpToken = useSyncTexStore((s) => s.pdfJump?.token);
  const sourceJumpToken = useSyncTexStore((s) => s.sourceJump?.token);
  const sourceFindToken = useSyncTexStore((s) => s.sourceFind?.token);
  const seenPdfRef = useRef(pdfJumpToken);
  const seenSourceRef = useRef(sourceJumpToken);
  const seenFindRef = useRef(sourceFindToken);
  useEffect(() => {
    if (pdfJumpToken != null && pdfJumpToken !== seenPdfRef.current) {
      seenPdfRef.current = pdfJumpToken;
      if (!isSideBySide) setTabParam(null);
    }
    // Fire only on a new jump token; setTabParam reads live search params.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfJumpToken]);
  useEffect(() => {
    const toSource =
      (sourceJumpToken != null && sourceJumpToken !== seenSourceRef.current) ||
      (sourceFindToken != null && sourceFindToken !== seenFindRef.current);
    seenSourceRef.current = sourceJumpToken;
    seenFindRef.current = sourceFindToken;
    if (toSource && !isSideBySide) setTabParam(editorTabValue);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceJumpToken, sourceFindToken]);

  if (!doc || !project) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-3 text-sm">
        {t("header.notFound")}
      </div>
    );
  }

  // Pass the whole doc: its API source_file/output_file are the real paths
  // (team layouts prefix the author base) and owner_name feeds the title.
  const meta = getDocMeta(doc.id, doc, project.lang ?? "ru");
  const stMeta = getStatusMeta(doc.status);

  const fullPath = `${project.folder}/${meta.file}`;

  const hasDocErrors = (doc.errors ?? 0) > 0;
  const docIssues = (doc.errors ?? 0) + (doc.warnings ?? 0);

  const PAGE_SEGMENTS: readonly {
    id: DocView;
    param: string;
    icon: LucideIcon;
    label: string;
    title: string;
  }[] = [
    {
      id: "checks",
      param: "checks",
      icon: ListChecks,
      label: t("workbench:dock.issues"),
      title: t("workbench:dock.issues"),
    },
    {
      id: "compile",
      param: "compile",
      icon: Terminal,
      label: t("workbench:dock.build"),
      title: t("workbench:dock.build"),
    },
    {
      id: "history",
      param: "history",
      icon: Clock,
      label: t("workbench:dock.history"),
      title: t("workbench:dock.history"),
    },
    {
      id: "signatures",
      param: "signatures",
      icon: PenTool,
      label: t("workbench:doc.signatures"),
      title: t("workbench:doc.placeSignature"),
    },
  ];

  const segments: readonly ViewSegment[] = [
    {
      id: "preview",
      label: t("workbench:doc.preview"),
      icon: Eye,
      title: t("workbench:doc.preview"),
      isDisabled: false,
    },
    {
      id: "editor",
      label: isOfficeEditableArtifact
        ? t("workbench:doc.document")
        : t("workbench:doc.editor"),
      icon: isOfficeEditableArtifact ? FileEdit : Code,
      title: isOfficeEditableArtifact
        ? t("workbench:doc.document")
        : t("workbench:doc.editor"),
      isDisabled: false,
    },
    {
      id: "side",
      label: t("workbench:doc.sideBySide"),
      icon: Columns2,
      title: canSplit
        ? t("workbench:doc.sideBySideHint")
        : t("workbench:doc.sideBySideTooNarrow"),
      isDisabled: !canSplit,
    },
  ];

  const handleSelectView = (view: DocView) => {
    if (view === "side") {
      if (!canSplit) return;
      // Пара панелей — это превью и редактор. Любая открытая страница
      // (замечания/сборка/журнал/подписи) старше «Рядом», поэтому параметр
      // обязательно сбрасывается — иначе клик по «Рядом» выглядел бы
      // проигнорированным.
      if (pageView) setTabParam(null);
      setIsSplitRequested(true);
      return;
    }
    setIsSplitRequested(false);
    setTabParam(view === "editor" ? editorTabValue : null);
  };

  // Стрелки ходят только по доступным сегментам: заблокированный «Рядом»
  // не должен ловить фокус на узком экране.
  const handleSegmentNav = (key: string, index: number): boolean => {
    if (
      key !== "ArrowRight" &&
      key !== "ArrowLeft" &&
      key !== "Home" &&
      key !== "End"
    ) {
      return false;
    }
    const enabled = segments.filter((segment) => !segment.isDisabled);
    if (enabled.length === 0) return false;
    const current = Math.max(
      enabled.findIndex((segment) => segment.id === segments[index]?.id),
      0,
    );
    const step = key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0;
    const targetIndex =
      key === "Home"
        ? 0
        : key === "End"
          ? enabled.length - 1
          : (current + step + enabled.length) % enabled.length;
    const target = enabled[targetIndex];
    if (!target) return false;
    handleSelectView(target.id);
    requestAnimationFrame(() => {
      document.getElementById(`document-tab-${target.id}`)?.focus();
    });
    return true;
  };

  const handleCopyPath = () => {
    navigator.clipboard
      .writeText(fullPath)
      .then(() => {
        toast.info(t("header.pathCopied"));
      })
      .catch(() => {
        toast.error(t("header.copyFailed"));
      });
  };

  const handleRevertCustomFile = () => {
    removeCustomFile(false)
      .then(() => {
        toast.success(t("customFile.revertedToast"));
        setRevertConfirmOpen(false);
      })
      .catch(() => {
        // per-request error toast already shown by the axios interceptor
      });
  };

  const editors = editorsData?.editors ?? [];
  const availableEditors = editors.filter((e) => e.available);
  const hasAnyEditor = availableEditors.length > 0;

  const menuItemClass = clsx(
    "flex cursor-pointer select-none items-center gap-2 outline-none",
    "focus:bg-bg-hover",
  );

  const previewNode = <PreviewPane project={project} doc={doc} />;

  const editorNode = isOfficeEditableArtifact ? (
    // Keyed by doc: switching documents must remount the pane (fresh fetch +
    // editor teardown) instead of reusing a stale session.
    <OfficeEditorPane
      key={`${projectId}:${docId}`}
      projectId={projectId}
      docId={docId}
    />
  ) : (
    <SourcePane projectId={projectId} doc={doc} />
  );

  return (
    <div
      className="flex flex-col"
      style={{ minHeight: 0, minWidth: 0, flex: 1 }}
    >
      <div
        className="document-workspace-header flex items-center"
        style={{
          padding: "12px 18px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
          gap: 14,
        }}
      >
        <div
          className="document-workspace-icon flex items-center justify-center shrink-0"
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            background: "var(--bg-2)",
            border: "1px solid var(--border)",
            color: "var(--accent)",
          }}
        >
          <FileText size={16} />
        </div>
        <div className="flex flex-col flex-1 min-w-0" style={{ gap: 2 }}>
          <div className="flex items-center gap-2 min-w-0">
            <span className="mono dim shrink-0" style={{ fontSize: 11 }}>
              {meta.code} ·
            </span>
            <h2
              className="truncate"
              style={{ margin: 0, fontSize: 14.5, fontWeight: 600 }}
            >
              {meta.name}
            </h2>
            <span className={"sev shrink-0 " + stMeta.sev}>
              <span className={"dot " + stMeta.sev} />
              {stMeta.label}
            </span>
            {doc.custom_file != null && (
              <span
                className="chip shrink-0"
                style={{
                  fontSize: 9.5,
                  background: "var(--bg-3)",
                  color: "var(--fg-2)",
                }}
              >
                {t("customFile.badge")}
              </span>
            )}
          </div>
          <div
            className="document-workspace-meta flex items-center mono"
            style={{
              fontSize: 10.5,
              color: "var(--fg-3)",
              gap: 8,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {doc.custom_file != null ? (
              <span className="shrink-0" title={doc.custom_file.ext}>
                {doc.custom_file.original_filename}
              </span>
            ) : (
              <>
                <span className="shrink-0">{meta.file}</span>
                <span className="shrink-0">·</span>
                <span className="shrink-0">{meta.gost}</span>
              </>
            )}
            {doc.pages != null && (
              <>
                <span className="shrink-0">·</span>
                <span className="shrink-0">
                  {t("header.pages", { count: doc.pages })}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="document-workspace-actions flex items-center gap-2 shrink-0">
          <button
            type="button"
            className="btn primary document-build-action"
            onClick={handleBuild}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <RefreshCw size={11} className="spin" />
                {t("header.building")}
              </>
            ) : hasPriorBuild ? (
              <>
                <RefreshCw size={11} />
                {t("header.rebuild")}
              </>
            ) : (
              <>
                <Play size={11} />
                {t("header.build")}
              </>
            )}
          </button>
        </div>
      </div>

      <div
        className="tabs"
        style={{
          padding: "5px 10px 5px 14px",
          alignItems: "center",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <div className="seg" role="tablist" aria-label={t("tabs.ariaLabel")}>
          {segments.map((segment, index) => {
            const Icon = segment.icon;
            const isActive = activeView === segment.id;
            return (
              <button
                key={segment.id}
                id={`document-tab-${segment.id}`}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls="document-tab-panel"
                tabIndex={isActive ? 0 : -1}
                title={segment.title}
                disabled={segment.isDisabled}
                className={clsx(isActive && "active")}
                style={
                  segment.isDisabled
                    ? { opacity: 0.45, cursor: "default" }
                    : undefined
                }
                onClick={() => {
                  handleSelectView(segment.id);
                }}
                onKeyDown={(event) => {
                  if (handleSegmentNav(event.key, index)) {
                    event.preventDefault();
                  }
                }}
              >
                <Icon size={12} />
                {segment.label}
              </button>
            );
          })}
        </div>

        {/* Проверки / Сборка / Журнал — отдельные страницы центра, а не вкладки
            нижней панели: в этом приложении центр показывает что угодно про
            документ, а не только сам документ. */}
        <div className="seg" role="group" aria-label={t("tabs.ariaLabel")}>
          {PAGE_SEGMENTS.map((entry) => {
            const Icon = entry.icon;
            const isActive = activeView === entry.id;
            return (
              <button
                key={entry.id}
                type="button"
                title={entry.title}
                aria-pressed={isActive}
                className={clsx(isActive && "active")}
                onClick={() => {
                  // Повторный клик возвращает к превью — страница не должна
                  // становиться ловушкой без очевидного выхода.
                  setTabParam(isActive ? null : entry.param);
                }}
              >
                <Icon size={12} />
                {entry.label}
                {entry.id === "checks" && docIssues > 0 && (
                  <span
                    className="mono"
                    style={{
                      fontSize: 9.5,
                      color: hasDocErrors ? "var(--c-err)" : "var(--c-warn)",
                    }}
                  >
                    {docIssues}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1" style={{ marginLeft: "auto" }}>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                className="icon-btn tt"
                data-tt={t("workbench:doc.moreActions")}
                aria-label={t("workbench:doc.moreActions")}
              >
                <MoreHorizontal size={14} />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                className={clsx(
                  "z-50 min-w-[14rem] overflow-hidden rounded-r-3 border border-border bg-bg-1",
                  "shadow-elev-pop",
                  "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
                  "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
                  "origin-top-right",
                )}
                sideOffset={6}
                align="end"
              >
                <DropdownMenu.Item
                  className={menuItemClass}
                  style={{ padding: "8px 12px", fontSize: 12.5 }}
                  onSelect={() => {
                    setUploadOpen(true);
                  }}
                >
                  <Upload size={12} />
                  <span>{t("customFile.replaceMenuItem")}</span>
                </DropdownMenu.Item>
                {doc.custom_file != null && (
                  <DropdownMenu.Item
                    className={menuItemClass}
                    style={{ padding: "8px 12px", fontSize: 12.5 }}
                    onSelect={() => {
                      setRevertConfirmOpen(true);
                    }}
                  >
                    <RefreshCw size={12} />
                    <span>{t("customFile.revertMenuItem")}</span>
                  </DropdownMenu.Item>
                )}
                {doc.custom_file != null && (
                  <DropdownMenu.Item asChild>
                    <a
                      href={customFileDownloadUrl(
                        project.id,
                        doc.output_file ?? "",
                      )}
                      download
                      className={menuItemClass}
                      style={{ padding: "8px 12px", fontSize: 12.5 }}
                    >
                      <Download size={12} />
                      <span>{t("customFile.downloadMenuItem")}</span>
                    </a>
                  </DropdownMenu.Item>
                )}
                <DropdownMenu.Item
                  className={menuItemClass}
                  style={{ padding: "8px 12px", fontSize: 12.5 }}
                  onSelect={handleCopyPath}
                >
                  <Copy size={12} />
                  <span>{t("header.copyPath")}</span>
                </DropdownMenu.Item>

                <div className="divider" style={{ margin: "4px 0" }} />
                <div
                  className="label-up dimmer"
                  style={{
                    padding: "4px 12px 6px",
                    fontSize: 9.5,
                    letterSpacing: "0.1em",
                  }}
                >
                  {t("header.openInEditor")}
                </div>
                {!hasAnyEditor && (
                  <div
                    className="dim"
                    style={{ padding: "0 12px 8px", fontSize: 11.5 }}
                  >
                    {t("header.noEditorsDetected")}
                  </div>
                )}
                {availableEditors.map((e) => (
                  <DropdownMenu.Item
                    key={e.id}
                    className={clsx(
                      "group relative flex cursor-pointer select-none items-center gap-3 outline-none",
                      "transition-colors",
                      "focus:bg-bg-hover",
                    )}
                    style={{ padding: "8px 12px" }}
                    onSelect={() => {
                      openInEditor(e.scheme, fullPath, 1);
                    }}
                  >
                    <div
                      className="flex items-center justify-center shrink-0"
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: 6,
                        background: "var(--bg-2)",
                        border: "1px solid var(--border)",
                        color: "var(--fg-0)",
                      }}
                    >
                      <EditorIcon editorId={e.id} size={15} />
                    </div>
                    <div className="flex flex-col min-w-0" style={{ gap: 1 }}>
                      <span
                        className="text-fg-0 group-focus:text-fg-0"
                        style={{
                          fontSize: 13,
                          fontWeight: 500,
                          lineHeight: 1.2,
                        }}
                      >
                        {e.label}
                      </span>
                      <span
                        className="mono dimmer"
                        style={{ fontSize: 10, lineHeight: 1.2 }}
                      >
                        {e.scheme}://
                      </span>
                    </div>
                    <ExternalLink
                      size={11}
                      className="ml-auto shrink-0 text-fg-3 opacity-0 transition-opacity group-focus:opacity-100"
                    />
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>

      <div
        id="document-tab-panel"
        role="tabpanel"
        aria-labelledby={`document-tab-${activeView}`}
        tabIndex={0}
        ref={setPaneEl}
        className="flex flex-col"
        style={{
          background: "var(--bg-0)",
          minHeight: 0,
          overflow: "hidden",
          flex: 1,
        }}
      >
        {activeView === "signatures" ? (
          <DocSignaturesPane projectId={projectId} docId={docId} />
        ) : activeView === "checks" ? (
          <ChecksPane projectId={projectId} docId={docId} />
        ) : activeView === "compile" ? (
          <CompilePane projectId={projectId} doc={doc} />
        ) : activeView === "history" ? (
          <HistoryPane projectId={projectId} docId={docId} />
        ) : isSideBySide ? (
          <div
            style={{
              flex: 1,
              minHeight: 0,
              display: "grid",
              // minmax(0, 1fr) (не 1fr ≡ minmax(auto, 1fr)) — иначе колонка не
              // умеет стать уже своего содержимого и PDF распирает раскладку.
              gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
              overflow: "hidden",
            }}
          >
            <div
              className="flex flex-col"
              style={{ minWidth: 0, minHeight: 0, overflow: "hidden" }}
            >
              {previewNode}
            </div>
            <div
              className="flex flex-col"
              style={{
                minWidth: 0,
                minHeight: 0,
                overflow: "hidden",
                borderLeft: "1px solid var(--border)",
              }}
            >
              {editorNode}
            </div>
          </div>
        ) : activeView === "editor" ? (
          editorNode
        ) : (
          previewNode
        )}
      </div>

      <UploadCustomFileModal
        isOpen={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
        }}
        projectId={projectId}
        docId={docId}
        docName={meta.name}
      />
      <Modal
        isOpen={revertConfirmOpen}
        onClose={() => {
          setRevertConfirmOpen(false);
        }}
        title={t("customFile.revertConfirmTitle")}
        description={t("customFile.revertConfirmDescription")}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setRevertConfirmOpen(false);
              }}
              disabled={isRevertingCustomFile}
            >
              {t("customFile.cancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={handleRevertCustomFile}
              disabled={isRevertingCustomFile}
            >
              {isRevertingCustomFile && <Spinner size="sm" />}
              {t("customFile.revertConfirmAction")}
            </button>
          </>
        }
      />
    </div>
  );
};
