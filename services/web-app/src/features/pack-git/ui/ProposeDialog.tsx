import { useId, useState } from "react";
import { CircleCheck, ExternalLink, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  forkRequired,
  lintFailure,
  packErrorText,
  useProposePack,
  type ForkRequired,
  type LintFailure,
  type PackForkChoice,
  type PackGit,
  type PackProposeResponse,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, Input, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { ChangedFiles } from "./ChangedFiles";

export type ProposeDialogProps = {
  git: PackGit;
  isOpen: boolean;
  onClose: () => void;
  editorDirty: boolean;
  /** Проверки пака не прошли: находки уходят в «Проблемы». */
  onLintFailed: (failure: LintFailure) => void;
  /** Открыть «Доступ к репозиторию» (отказ в push, нет прав на PR). */
  onAccess: () => void;
};

type Step =
  | { kind: "form" }
  | { kind: "fork"; info: ForkRequired }
  | { kind: "done"; result: PackProposeResponse };

type ForkMode = "create" | "url";

const prWord = (provider: PackGit["provider"]): "mr" | "pr" =>
  provider === "gitlab" ? "mr" : "pr";

const trimmed = (value: string): string | null => {
  const text = value.trim();
  return text === "" ? null : text;
};

/** Итог «Предложить изменения»: PR или MR, ссылка compare, сводка проверок. */
const ProposeResult = ({
  result,
  provider,
  onAccess,
}: {
  result: PackProposeResponse;
  provider: PackGit["provider"];
  onAccess: () => void;
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const word = prWord(provider);
  const pull = result.pull_request;
  const fork = result.git.workspace.fork_url !== null;
  const warnings = result.checks.findings.filter(
    (f) => f.severity === "warning",
  );
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.75rem" }}
      data-testid="git-propose-done"
    >
      <div className="ps-access-row">
        <CircleCheck size="1rem" aria-hidden="true" className="ps-ci-ok" />
        <div className="ps-access-text">
          <strong>
            {pull
              ? pull.created
                ? t(`git.propose.opened.${word}`, { number: pull.number })
                : t(`git.propose.existing.${word}`, { number: pull.number })
              : t("git.propose.pushed")}
          </strong>
          <span className="mono truncate" title={result.pushed_to}>
            {fork
              ? t("git.propose.toFork", { url: result.pushed_to })
              : t("git.propose.toRepo", { url: result.pushed_to })}
          </span>
        </div>
      </div>
      {pull && (
        <a
          href={pull.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn primary"
          style={{
            gap: "0.375rem",
            textDecoration: "none",
            alignSelf: "flex-start",
          }}
          data-testid="git-propose-pr-link"
        >
          <ExternalLink size="0.75rem" aria-hidden="true" />
          {t(`git.propose.openPr.${word}`, { number: pull.number })}
        </a>
      )}
      {result.pr_error && (
        <Notice
          tone="warn"
          role="alert"
          text={
            i18n.exists(`errors:code.${result.pr_error.code}`)
              ? t(`errors:code.${result.pr_error.code}`)
              : result.pr_error.detail
          }
          action={
            <Button size="xs" variant="secondary" onClick={onAccess}>
              {t("git.access.title")}
            </Button>
          }
        />
      )}
      {!pull && result.compare_url && (
        <a
          href={result.compare_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn primary"
          style={{
            gap: "0.375rem",
            textDecoration: "none",
            alignSelf: "flex-start",
          }}
          data-testid="git-propose-compare"
        >
          <ExternalLink size="0.75rem" aria-hidden="true" />
          {t(`git.propose.compare.${word}`)}
        </a>
      )}
      {result.checks.classes.length > 0 && (
        <section>
          <h3 className="ps-problems-group">{t("git.propose.classes")}</h3>
          <ul className="ps-git-notes">
            {result.checks.classes.map((item) => (
              <li key={item.path}>
                <span className="mono">{item.path.split("/").pop()}</span>
                {": "}
                {pickLocalized(item.headline, i18n.language, item.suggested)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {warnings.length > 0 && (
        <section>
          <h3 className="ps-problems-group">
            {t("problems.warnings", { count: warnings.length })}
          </h3>
          <ul className="ps-git-notes">
            {warnings.map((item, index) => (
              <li key={`${item.path}:${String(index)}`}>
                <TriangleAlert
                  size="0.75rem"
                  aria-hidden="true"
                  className="ps-problem-warning"
                />{" "}
                {item.message}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="ps-dialog-text">{t("git.propose.ciHint")}</p>
    </div>
  );
};

/**
 * «Предложить изменения» (template-studio.md, 4.3): коммит несохранённого,
 * проверки пака, push рабочей ветки и PR GitHub или MR GitLab. Нет права push:
 * шаг «Отправить в форк» (свой адрес или новый форк токеном на GitHub).
 */
export const ProposeDialog = ({
  git,
  isOpen,
  onClose,
  editorDirty,
  onLintFailed,
  onAccess,
}: ProposeDialogProps) => {
  const { t } = useTranslation("packStudio");
  const propose = useProposePack(git.workspace.id);
  const [step, setStep] = useState<Step>({ kind: "form" });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [forkMode, setForkMode] = useState<ForkMode>("url");
  const [forkUrl, setForkUrl] = useState("");
  const uid = useId();
  const word = prWord(git.provider);
  const ws = git.workspace;

  const reset = () => {
    propose.reset();
    setStep({ kind: "form" });
    setTitle("");
    setDescription("");
    setMessage("");
    setForkMode("url");
    setForkUrl("");
  };
  const close = () => {
    if (propose.isPending) return;
    reset();
    onClose();
  };

  const send = (fork: PackForkChoice | null) => {
    propose.mutate(
      {
        title: trimmed(title),
        description: trimmed(description),
        message: git.dirty ? trimmed(message) : null,
        ...(fork ? { fork } : {}),
      },
      {
        onSuccess: (result) => {
          setStep({ kind: "done", result });
        },
        onError: (error) => {
          const failed = lintFailure(error);
          if (failed) {
            reset();
            onClose();
            onLintFailed(failed);
            return;
          }
          const fork = forkRequired(error);
          if (fork) {
            setForkMode(
              fork.canCreate && !ws.service_access ? "create" : "url",
            );
            setStep({ kind: "fork", info: fork });
          }
        },
      },
    );
  };

  const error = propose.error;
  // fork_required уже разобран шагом «форк»: его текст показывает сам шаг.
  const shownError =
    error && !forkRequired(error) && !lintFailure(error) ? error : null;
  const denied =
    shownError instanceof ApiError && shownError.code === "push_denied";

  let body: React.ReactNode;
  let footer: React.ReactNode;
  if (step.kind === "done") {
    body = (
      <ProposeResult
        result={step.result}
        provider={git.provider}
        onAccess={onAccess}
      />
    );
    footer = <Button onClick={close}>{t("git.propose.close")}</Button>;
  } else if (step.kind === "fork") {
    const canCreate = step.info.canCreate && !ws.service_access;
    const reason = step.info.reason;
    body = (
      <div
        className="flex flex-col"
        style={{ gap: "0.625rem" }}
        data-testid="git-fork-step"
      >
        <Notice tone="info" role="status" text={t("git.fork.lead")} />
        {reason && (
          <Notice
            tone="err"
            role="alert"
            text={t(`git.fork.reason.${reason}`, {
              defaultValue: t("errors:code.fork_required"),
            })}
          />
        )}
        {canCreate && (
          <label className="ps-choice" htmlFor={`${uid}-create`}>
            <input
              id={`${uid}-create`}
              type="radio"
              name={`${uid}-fork`}
              checked={forkMode === "create"}
              onChange={() => {
                setForkMode("create");
              }}
              style={{ accentColor: "var(--accent)" }}
              data-testid="git-fork-create"
            />
            <span className="ps-choice-text">
              <span>{t("git.fork.create")}</span>
              <span className="ps-choice-hint">{t("git.fork.createHint")}</span>
            </span>
          </label>
        )}
        {canCreate && (
          <label className="ps-choice" htmlFor={`${uid}-url`}>
            <input
              id={`${uid}-url`}
              type="radio"
              name={`${uid}-fork`}
              checked={forkMode === "url"}
              onChange={() => {
                setForkMode("url");
              }}
              style={{ accentColor: "var(--accent)" }}
            />
            <span className="ps-choice-text">
              <span>{t("git.fork.own")}</span>
              <span className="ps-choice-hint">{t("git.fork.ownHint")}</span>
            </span>
          </label>
        )}
        {(forkMode === "url" || !canCreate) && (
          <Input
            label={t("git.fork.url")}
            hint={t("git.fork.urlHint")}
            placeholder="https://github.com/me/packs.git"
            value={forkUrl}
            maxLength={2048}
            onChange={(e) => {
              setForkUrl(e.target.value);
            }}
            isMono
            data-testid="git-fork-url"
          />
        )}
        {shownError !== null && (
          <Notice tone="err" role="alert" text={packErrorText(shownError)} />
        )}
      </div>
    );
    const useCreate = canCreate && forkMode === "create";
    footer = (
      <>
        <Button
          variant="secondary"
          disabled={propose.isPending}
          onClick={() => {
            propose.reset();
            setStep({ kind: "form" });
          }}
        >
          {t("git.fork.back")}
        </Button>
        <Button
          disabled={
            propose.isPending || (!useCreate && trimmed(forkUrl) === null)
          }
          onClick={() => {
            send(useCreate ? { create: true } : { url: forkUrl.trim() });
          }}
          data-testid="git-fork-submit"
        >
          {propose.isPending ? t("git.propose.sending") : t("git.fork.submit")}
        </Button>
      </>
    );
  } else {
    body = (
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {editorDirty && (
          <Notice tone="warn" role="status" text={t("git.editorDirty")} />
        )}
        <p className="ps-dialog-text">
          {t(`git.propose.where.${word}`, {
            branch: git.branch ?? t("git.propose.autoBranch"),
            base: git.base_branch ?? "",
          })}
        </p>
        {ws.service_access && (
          <p className="ps-dialog-text">{t("git.propose.service")}</p>
        )}
        {ws.fork_url && (
          <p className="ps-dialog-text mono">
            {t("git.propose.viaFork", { url: ws.fork_url })}
          </p>
        )}
        <details className="sync-details">
          <summary>
            {t("git.propose.files", { count: git.changed.length })}
          </summary>
          <ChangedFiles files={git.changed} />
        </details>
        <Input
          label={t(`git.propose.title.${word}`)}
          hint={t("git.propose.titleHint")}
          value={title}
          maxLength={200}
          onChange={(e) => {
            setTitle(e.target.value);
          }}
          data-testid="git-propose-title"
        />
        <Textarea
          label={t("git.propose.description")}
          hint={t("git.propose.descriptionHint")}
          value={description}
          maxLength={20000}
          rows={4}
          onChange={(e) => {
            setDescription(e.target.value);
          }}
        />
        {git.dirty && (
          <Input
            label={t("git.propose.message")}
            hint={t("git.propose.messageHint", {
              count: git.uncommitted.length,
            })}
            value={message}
            maxLength={2000}
            onChange={(e) => {
              setMessage(e.target.value);
            }}
            isMono
          />
        )}
        <p className="ps-dialog-text">{t("git.propose.checksHint")}</p>
        {shownError !== null && (
          <Notice
            tone="err"
            role="alert"
            text={packErrorText(shownError)}
            action={
              denied ? (
                <Button size="xs" variant="secondary" onClick={onAccess}>
                  {t("git.access.title")}
                </Button>
              ) : undefined
            }
          />
        )}
      </div>
    );
    footer = (
      <>
        <Button variant="secondary" onClick={close}>
          {t("common.cancel")}
        </Button>
        <Button
          disabled={propose.isPending}
          onClick={() => {
            send(null);
          }}
          data-testid="git-propose-submit"
        >
          {propose.isPending
            ? t("git.propose.sending")
            : t(`git.propose.submit.${word}`)}
        </Button>
      </>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={step.kind === "fork" ? t("git.fork.title") : t("propose.label")}
      width={600}
      footer={footer}
    >
      <div data-testid="git-propose">{body}</div>
    </Modal>
  );
};
