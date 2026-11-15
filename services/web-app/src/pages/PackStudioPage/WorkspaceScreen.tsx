import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  FileSearch,
  FolderTree,
  Lock,
  RefreshCw,
} from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  findVersion,
  findingTarget,
  packErrorText,
  packStudioKeys,
  usePackTree,
  usePackWorkspace,
  useRefreshPackWorkspace,
  versionDirOf,
  workspaceErrorText,
  type LintFailure,
  type PackWorkspace,
} from "@entities/pack-studio";
import { PackFileEditor } from "@features/pack-file-editor";
import { PackGitBar } from "@features/pack-git";
import { PackPlacesEditor } from "@features/pack-places";
import { PackPreviewPane } from "@features/pack-preview";
import { PackTreePanel, versionStatusVariant } from "@features/pack-tree";
import {
  NewVersionDialog,
  VersionBar,
  type NewVersionTarget,
} from "@features/pack-version";
import {
  WorkspaceStateBadge,
  workspaceSource,
} from "@features/pack-workspaces";
import { useIsPhoneWidth } from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  Modal,
  Spinner,
  type RevealRequest,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

/** Крошки открытого файла: пак, шаблон, версия со статусом и замком, путь в версии. */
const FileCrumbs = ({
  workspaceId,
  path,
}: {
  workspaceId: string;
  path: string;
}) => {
  const { t } = useTranslation("packStudio");
  const tree = usePackTree(workspaceId);
  const found = findVersion(tree.data, path);
  const versionDir = versionDirOf(path);
  const rest = versionDir ? path.slice(versionDir.length + 1) : path;
  return (
    <nav
      className="ps-crumbs"
      aria-label={t("crumbs.label")}
      data-testid="ps-crumbs"
    >
      {found ? (
        <>
          <span>{found.packId}</span>
          <span aria-hidden="true">›</span>
          <span>{found.templateId}</span>
          <span aria-hidden="true">›</span>
          <span className="ps-crumb-version">
            {found.version.version}
            {found.version.status && (
              <span
                className={`ps-mark ps-mark-${versionStatusVariant(found.version.status)}`}
              >
                {found.version.status}
              </span>
            )}
            {found.version.released && (
              <span className="ps-mark ps-mark-lock" title={t("tree.released")}>
                <Lock size="0.625rem" aria-hidden="true" />
              </span>
            )}
          </span>
          <span aria-hidden="true">›</span>
          <span className="mono truncate">{rest}</span>
        </>
      ) : (
        <span className="mono truncate">{path}</span>
      )}
    </nav>
  );
};

/** Пространство не готово: клон идёт или не удался. */
const NotReady = ({ workspace }: { workspace: PackWorkspace }) => {
  const { t } = useTranslation("packStudio");
  const refresh = useRefreshPackWorkspace();
  if (workspace.state === "cloning") {
    return (
      <EmptyState
        framed
        icon={<Spinner size="md" />}
        title={t("workspace.cloningTitle")}
        description={t("workspace.cloningLead")}
        testId="ws-cloning"
      />
    );
  }
  return (
    <ErrorState
      framed
      title={t("workspace.failedTitle")}
      description={
        workspace.error
          ? workspaceErrorText(workspace.error)
          : t("workspace.failedLead")
      }
      onRetry={() => {
        refresh.mutate(workspace.id);
      }}
      retrying={refresh.isPending}
      testId="ws-failed"
    />
  );
};

type PendingOpen = { path: string; line: number | null };

/**
 * Рабочее пространство: дерево слева, редактор файла по центру, «Проблемы» и
 * предпросмотр справа. Открытый файл живёт в адресе (`?file=`): ссылку можно
 * отправить и открыть заново. Несохранённая правка не теряется при переходе к
 * другому файлу: сначала вопрос.
 */
export const WorkspaceScreen = () => {
  const { t } = useTranslation("packStudio");
  const { workspaceId = "" } = useParams<{ workspaceId: string }>();
  const [params, setParams] = useSearchParams();
  const file = params.get("file");
  const workspace = usePackWorkspace(workspaceId);
  const refresh = useRefreshPackWorkspace();
  const phone = useIsPhoneWidth();
  const [treeOpen, setTreeOpen] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [reveal, setReveal] = useState<
    (RevealRequest & { path: string }) | null
  >(null);
  const [pending, setPending] = useState<PendingOpen | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  // Находки проверки перед «Предложить изменения» и запрос показать «Проблемы».
  const [gate, setGate] = useState<LintFailure | null>(null);
  const [problemsFocus, setProblemsFocus] = useState(0);
  // Операция git поменяла файлы на диске: редактор открывает файл заново.
  const [reload, setReload] = useState(0);
  // Мастер «Новая версия»: шаблон, для которого открыт шаг 1.
  const [newVersion, setNewVersion] = useState<NewVersionTarget | null>(null);
  // Места подписей записаны в манифест версии: проверки заново, PDF при этом не устаревает.
  const [placesSaves, setPlacesSaves] = useState(0);
  const client = useQueryClient();
  const dirtyRef = useRef(false);
  const tokenRef = useRef(0);

  const go = useCallback(
    (path: string, line: number | null) => {
      setTreeOpen(false);
      if (path !== file) {
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.set("file", path);
            return next;
          },
          { replace: false },
        );
      }
      if (line !== null) {
        tokenRef.current += 1;
        setReveal({ path, line, token: tokenRef.current });
      }
    },
    [file, setParams],
  );

  const open = useCallback(
    (path: string, line: number | null = null) => {
      if (dirtyRef.current && path !== file) {
        setPending({ path, line });
        return;
      }
      go(path, line);
    },
    [file, go],
  );

  const onDirtyChange = useCallback((dirty: boolean) => {
    dirtyRef.current = dirty;
    setEditorDirty(dirty);
  }, []);

  const onLintFailed = useCallback(
    (failure: LintFailure) => {
      setGate(failure);
      setProblemsFocus((n) => n + 1);
      // Файл не открыт: открыть первую находку, «Проблемы» видны рядом с ней.
      if (file === null) {
        const first = failure.findings
          .map((f) => findingTarget(f.path, f.message))
          .find((target) => target !== null);
        if (first) go(first.path, first.line);
      }
    },
    [file, go],
  );

  // Места подписей записали манифест: открытый он же без правок открывается заново (после свежего
  // чтения файла), с правками его запись упрётся в «файл изменился» и покажет, что делать. Сам
  // редактор с предпросмотром не пересоздаётся: окно мест остаётся открытым.
  const [contentRevision, setContentRevision] = useState(0);
  const onPlacesSaved = useCallback(
    (path: string) => {
      setPlacesSaves((n) => n + 1);
      if (path !== file || dirtyRef.current) return;
      void client
        .refetchQueries({ queryKey: packStudioKeys.file(workspaceId, path) })
        .then(() => {
          if (!dirtyRef.current) setContentRevision((n) => n + 1);
        });
    },
    [client, file, workspaceId],
  );

  const onFilesChanged = useCallback(() => {
    dirtyRef.current = false;
    setEditorDirty(false);
    setReload((n) => n + 1);
    setEpoch((n) => n + 1);
  }, []);

  if (workspace.isPending) {
    return (
      <div className="ps-page flex justify-center">
        <Spinner size="lg" />
      </div>
    );
  }
  if (workspace.isError) {
    return (
      <div className="ps-page">
        <ErrorState
          framed
          description={packErrorText(workspace.error)}
          onRetry={() => void workspace.refetch()}
        />
        <Link to={PACK_STUDIO_PATH} className="ps-link">
          {t("workspace.back")}
        </Link>
      </div>
    );
  }

  const ws = workspace.data;
  const ready = ws.state === "ready";
  const tree = (
    <PackTreePanel
      workspaceId={ws.id}
      selectedPath={file}
      onSelect={(path) => {
        open(path);
      }}
      onNewVersion={(pack, template) => {
        setTreeOpen(false);
        setNewVersion({ pack, template });
      }}
    />
  );

  return (
    <div className="ps-workspace" data-testid="ps-workspace">
      <header className="ps-ws-head">
        <Link
          to={PACK_STUDIO_PATH}
          className="icon-btn"
          aria-label={t("workspace.back")}
          title={t("workspace.back")}
          data-testid="ws-back"
        >
          <ArrowLeft size="0.9375rem" />
        </Link>
        <div className="ps-ws-head-text">
          <div className="ps-ws-title">
            <h1 className="ps-ws-name truncate">{ws.label}</h1>
            <WorkspaceStateBadge workspace={ws} />
          </div>
          <div className="ps-ws-meta mono truncate" title={workspaceSource(ws)}>
            {workspaceSource(ws)}
          </div>
        </div>
        <div className="ps-ws-head-actions">
          {phone && ready && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setTreeOpen(true);
              }}
              data-testid="ws-tree-open"
            >
              <FolderTree size="0.875rem" />
              {t("tree.title")}
            </Button>
          )}
          {ws.kind === "git" && ready && (
            <Button
              size="sm"
              variant="ghost"
              disabled={ws.busy || refresh.isPending}
              onClick={() => {
                refresh.mutate(ws.id);
              }}
              title={t("workspaces.refreshHint")}
              data-testid="ws-refresh"
            >
              <RefreshCw size="0.75rem" />
              <span className="ps-hide-phone">{t("workspaces.refresh")}</span>
            </Button>
          )}
        </div>
      </header>
      {ws.error && ready && (
        <Notice tone="warn" role="status" text={workspaceErrorText(ws.error)} />
      )}
      {ws.kind === "git" && ready && (
        <PackGitBar
          workspace={ws}
          editorDirty={editorDirty}
          onOpenFile={(path) => {
            open(path);
          }}
          onLintFailed={onLintFailed}
          onFilesChanged={onFilesChanged}
        />
      )}
      {!ready ? (
        <div className="ps-page">
          <NotReady workspace={ws} />
        </div>
      ) : (
        <div className="ps-ws-body-grid">
          {!phone && <div className="ps-ws-tree">{tree}</div>}
          <div className="ps-ws-content">
            {file ? (
              <>
                <FileCrumbs workspaceId={ws.id} path={file} />
                <VersionBar
                  workspaceId={ws.id}
                  git={ws.kind === "git"}
                  path={file}
                  revision={epoch + placesSaves}
                  onOpenFile={(path) => {
                    open(path);
                  }}
                  onNewVersion={setNewVersion}
                  onFilesChanged={onFilesChanged}
                  editorDirty={editorDirty}
                />
                <PackFileEditor
                  key={`${file}:${String(reload)}`}
                  workspaceId={ws.id}
                  path={file}
                  lintEpoch={epoch + placesSaves}
                  onSaved={() => {
                    setEpoch((n) => n + 1);
                    // Правка на диске: «правки после коммита» в панели git, места подписей версии.
                    void client.invalidateQueries({
                      queryKey: packStudioKeys.git(ws.id),
                    });
                    void client.invalidateQueries({
                      queryKey: packStudioKeys.signaturesAll(ws.id),
                    });
                  }}
                  onOpenFile={open}
                  reveal={reveal?.path === file ? reveal : undefined}
                  onDirtyChange={onDirtyChange}
                  gate={gate}
                  onDismissGate={() => {
                    setGate(null);
                  }}
                  problemsFocus={problemsFocus}
                  contentRevision={contentRevision}
                  preview={
                    <PackPreviewPane
                      workspaceId={ws.id}
                      path={file}
                      revision={epoch}
                      places={(slot) => (
                        <PackPlacesEditor
                          workspaceId={ws.id}
                          {...slot}
                          onSaved={onPlacesSaved}
                        />
                      )}
                    />
                  }
                />
              </>
            ) : (
              <EmptyState
                framed
                icon={<FileSearch size="1.5rem" />}
                title={t("workspace.pickTitle")}
                description={t("workspace.pickLead")}
                action={
                  phone ? (
                    <Button
                      onClick={() => {
                        setTreeOpen(true);
                      }}
                    >
                      <FolderTree size="0.875rem" />
                      {t("tree.title")}
                    </Button>
                  ) : undefined
                }
                testId="ws-pick-file"
              />
            )}
          </div>
        </div>
      )}
      {phone && (
        <Modal
          isOpen={treeOpen}
          onClose={() => {
            setTreeOpen(false);
          }}
          title={t("tree.title")}
        >
          <div className="ps-tree-sheet">{tree}</div>
        </Modal>
      )}
      <NewVersionDialog
        workspaceId={ws.id}
        target={newVersion}
        onClose={() => {
          setNewVersion(null);
        }}
        onCreated={(created) => {
          setNewVersion(null);
          open(`${created.version.path}/version.yaml`);
        }}
      />
      <Modal
        isOpen={pending !== null}
        onClose={() => {
          setPending(null);
        }}
        title={t("leave.title")}
        description={t("leave.lead")}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setPending(null);
              }}
            >
              {t("leave.stay")}
            </Button>
            <Button
              variant="danger"
              data-testid="leave-discard"
              onClick={() => {
                const next = pending;
                setPending(null);
                dirtyRef.current = false;
                if (next) go(next.path, next.line);
              }}
            >
              {t("leave.discard")}
            </Button>
          </>
        }
      />
    </div>
  );
};
