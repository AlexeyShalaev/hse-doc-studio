import { useState } from "react";
import { useIsMutating } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ExternalLink,
  FileDiff,
  GitBranch,
  GitMerge,
  GitPullRequestArrow,
  GitFork,
  KeyRound,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  mergeConflictFiles,
  packErrorText,
  packStudioKeys,
  useMergePackBase,
  usePackChecks,
  usePackGit,
  type LintFailure,
  type PackWorkspace,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { ActionMenu, Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { BranchDialog } from "./BranchDialog";
import { ChecksDialog, CiBadge } from "./ChecksDialog";
import { CommitDialog } from "./CommitDialog";
import { DiffDialog } from "./DiffDialog";
import { MergeConflictDialog } from "./MergeConflictDialog";
import { ProposeDialog } from "./ProposeDialog";
import { RepoAccessDialog } from "./RepoAccessDialog";
import { StartOverDialog } from "./StartOverDialog";

export type PackGitBarProps = {
  workspace: PackWorkspace;
  /** В редакторе несохранённая правка: в версию и в PR она не попадёт. */
  editorDirty: boolean;
  onOpenFile: (path: string) => void;
  /** Проверки пака перед отправкой не прошли: находки в «Проблемы». */
  onLintFailed: (failure: LintFailure) => void;
  /** Операция поменяла файлы на диске (ветка, слияние, начать заново). */
  onFilesChanged: () => void;
};

type Dialog =
  "commit" | "branch" | "propose" | "diff" | "checks" | "access" | "startOver";

const prLabel = (workspace: PackWorkspace, provider: string): string =>
  `${provider === "gitlab" ? "MR !" : "PR #"}${String(workspace.pr_number ?? "")}`;

/**
 * Панель git рабочего пространства (template-studio.md, 4.3 и 4.6): ветка,
 * правки после коммита, отставание от основной ветки, PR и статус проверок;
 * «Сохранить версию», «Предложить изменения» и остальное в меню. Операции идут
 * синхронно под замком пространства: пока одна идёт, кнопки выключены.
 */
export const PackGitBar = ({
  workspace,
  editorDirty,
  onOpenFile,
  onLintFailed,
  onFilesChanged,
}: PackGitBarProps) => {
  const { t } = useTranslation("packStudio");
  const id = workspace.id;
  const git = usePackGit(id);
  const checks = usePackChecks(id, workspace.pushed_sha);
  const merge = useMergePackBase(id);
  const running = useIsMutating({ mutationKey: packStudioKeys.gitOp(id) }) > 0;
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [conflict, setConflict] = useState<string[] | null>(null);
  const close = () => {
    setDialog(null);
  };

  if (git.isPending) {
    return (
      <div className="ps-git-bar" data-testid="git-bar">
        <span className="ps-git-chip">
          <Spinner size="sm" />
          {t("git.loading")}
        </span>
      </div>
    );
  }
  if (git.isError) {
    return (
      <div className="ps-git-bar" data-testid="git-bar">
        <Notice
          tone="err"
          role="alert"
          text={packErrorText(git.error)}
          action={
            <Button
              size="xs"
              variant="secondary"
              onClick={() => void git.refetch()}
            >
              {t("workspaces.retry")}
            </Button>
          }
        />
      </div>
    );
  }

  const g = git.data;
  const busy = running || workspace.busy;
  const ws = g.workspace;
  const base = g.base_branch ?? "";

  const runMerge = () => {
    merge.mutate(undefined, {
      onSuccess: (next) => {
        toast.success(
          next.behind === 0 && g.behind === 0
            ? t("git.merge.upToDate", { base })
            : t("git.merge.done", { base }),
        );
        onFilesChanged();
      },
      onError: (error) => {
        const files = mergeConflictFiles(error);
        if (files) {
          merge.reset();
          setConflict(files);
        }
      },
    });
  };

  return (
    <div className="ps-git-bar" data-testid="git-bar">
      <div className="ps-git-info">
        <button
          type="button"
          className="ps-git-branch"
          onClick={() => {
            setDialog("branch");
          }}
          disabled={busy}
          title={t("git.branch.title")}
          data-testid="git-branch"
        >
          <GitBranch size="0.75rem" aria-hidden="true" />
          <span className="mono truncate">
            {g.branch ?? t("git.noBranch", { base })}
          </span>
        </button>
        <span
          className="ps-git-chip"
          data-testid="git-dirty"
          data-dirty={g.dirty ? "true" : "false"}
        >
          {g.dirty
            ? t("git.uncommitted", { count: g.uncommitted.length })
            : t("git.clean")}
        </span>
        {(g.ahead > 0 || g.behind > 0) && (
          <span
            className="ps-git-chip"
            title={t("git.aheadBehind", {
              ahead: g.ahead,
              behind: g.behind,
              base,
            })}
            data-testid="git-ahead-behind"
          >
            <ArrowUp size="0.6875rem" aria-label={t("git.ahead")} />
            {g.ahead}
            <ArrowDown size="0.6875rem" aria-label={t("git.behind")} />
            {g.behind}
          </span>
        )}
        {ws.service_access && (
          <span
            className="ps-git-chip ps-ci-ok"
            title={t("git.access.serviceLead")}
            data-testid="git-service-access"
          >
            <ShieldCheck size="0.6875rem" aria-hidden="true" />
            <span className="ps-hide-phone">{t("git.serviceAccess")}</span>
          </span>
        )}
        {ws.fork_url && (
          <span className="ps-git-chip" title={ws.fork_url}>
            <GitFork size="0.6875rem" aria-hidden="true" />
            <span className="ps-hide-phone">{t("git.fork.chip")}</span>
          </span>
        )}
        {ws.pr_url ? (
          <a
            href={ws.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ps-git-chip ps-git-link"
            data-testid="git-pr-link"
          >
            <GitPullRequestArrow size="0.6875rem" aria-hidden="true" />
            {prLabel(ws, g.provider)}
          </a>
        ) : (
          g.compare_url && (
            <a
              href={g.compare_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ps-git-chip ps-git-link"
              data-testid="git-compare-link"
            >
              <ExternalLink size="0.6875rem" aria-hidden="true" />
              {t("git.openCompare")}
            </a>
          )
        )}
        {ws.pushed_sha && (
          <CiBadge
            status={checks.data}
            loading={checks.isFetching}
            onClick={() => {
              setDialog("checks");
            }}
          />
        )}
      </div>
      <div className="ps-git-actions">
        {running && <Spinner size="sm" />}
        <Button
          size="xs"
          variant="ghost"
          onClick={() => {
            setDialog("diff");
          }}
          title={t("git.diff.title")}
          data-testid="git-diff-open"
        >
          <FileDiff size="0.6875rem" />
          <span className="ps-hide-phone">{t("git.diff.button")}</span>
        </Button>
        <Button
          size="xs"
          variant="secondary"
          disabled={busy || !g.dirty}
          onClick={() => {
            setDialog("commit");
          }}
          title={t("git.commit.title")}
          data-testid="git-commit"
        >
          <Save size="0.6875rem" />
          <span className="ps-hide-phone">{t("git.commit.button")}</span>
        </Button>
        <Button
          size="xs"
          disabled={busy || (g.changed.length === 0 && g.ahead === 0)}
          onClick={() => {
            setDialog("propose");
          }}
          title={t("propose.label")}
          data-testid="propose-changes"
        >
          <GitPullRequestArrow size="0.6875rem" />
          <span className="ps-hide-phone">{t("propose.label")}</span>
        </Button>
        <ActionMenu
          label={t("git.menu")}
          testId="git-menu"
          align="end"
          items={[
            {
              id: "branch",
              label: t("git.branch.title"),
              icon: <GitBranch size="0.875rem" />,
              disabled: busy,
              onSelect: () => {
                setDialog("branch");
              },
              testId: "git-menu-branch",
            },
            {
              id: "merge",
              label: t("git.merge.button", { base }),
              icon: <GitMerge size="0.875rem" />,
              disabled: busy || g.branch === null,
              onSelect: runMerge,
              testId: "git-menu-merge",
            },
            {
              id: "access",
              label: t("git.access.title"),
              icon: <KeyRound size="0.875rem" />,
              onSelect: () => {
                setDialog("access");
              },
              testId: "git-menu-access",
            },
            {
              id: "start-over",
              label: t("git.startOver.title"),
              icon: <RotateCcw size="0.875rem" />,
              danger: true,
              disabled: busy,
              onSelect: () => {
                setDialog("startOver");
              },
              testId: "git-menu-start-over",
            },
          ]}
        />
      </div>
      {merge.isError && (
        <div className="ps-git-notice">
          <Notice
            tone="err"
            role="alert"
            text={packErrorText(merge.error)}
            action={
              <Button
                size="xs"
                variant="ghost"
                onClick={() => {
                  merge.reset();
                }}
              >
                {t("git.dismiss")}
              </Button>
            }
          />
        </div>
      )}
      <CommitDialog
        git={g}
        isOpen={dialog === "commit"}
        onClose={close}
        editorDirty={editorDirty}
      />
      <BranchDialog
        git={g}
        isOpen={dialog === "branch"}
        onClose={close}
        onSwitched={onFilesChanged}
      />
      <ProposeDialog
        git={g}
        isOpen={dialog === "propose"}
        onClose={close}
        editorDirty={editorDirty}
        onLintFailed={onLintFailed}
        onAccess={() => {
          setDialog("access");
        }}
      />
      <StartOverDialog
        git={g}
        isOpen={dialog === "startOver"}
        onClose={close}
        onDone={onFilesChanged}
      />
      <DiffDialog
        workspaceId={id}
        baseBranch={g.base_branch}
        isOpen={dialog === "diff"}
        onClose={close}
      />
      <ChecksDialog
        workspaceId={id}
        pushedSha={ws.pushed_sha}
        isOpen={dialog === "checks"}
        onClose={close}
      />
      <RepoAccessDialog
        workspace={ws}
        isOpen={dialog === "access"}
        onClose={close}
      />
      <MergeConflictDialog
        files={conflict}
        baseBranch={g.base_branch}
        onClose={() => {
          setConflict(null);
        }}
        onOpen={onOpenFile}
      />
    </div>
  );
};
