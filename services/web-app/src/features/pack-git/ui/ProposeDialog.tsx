import { useCallback, useId, useMemo, useState } from "react";
import { CircleCheck, ExternalLink, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  forkRequired,
  lintFailure,
  usePackOfficial,
  useProposePack,
  type ForkRequired,
  type LintFailure,
  type PackForkChoice,
  type PackGit,
  type PackProposeResponse,
  type PackVersionRef,
  PackErrorText,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, Input, Modal, Textarea } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { impactVersions } from "../lib/impactVersions";
import { ChangedFiles } from "./ChangedFiles";
import { ImpactSlot, type ImpactReport } from "./ImpactSlot";

export type ProposeDialogProps = {
  git: PackGit;
  isOpen: boolean;
  onClose: () => void;
  editorDirty: boolean;
  /** Проверки пака не прошли: находки уходят в «Проблемы». */
  onLintFailed: (failure: LintFailure) => void;
  /** Открыть «Доступ к репозиторию» (отказ в push, нет прав на PR). */
  onAccess: () => void;
  /** Версия открытого экрана «Результат»: её «до и после» идёт первой. */
  version?: PackVersionRef | null;
  /** Адрес возврата из режима «Файлы» после «Открыть правило» (экран «Результат» со своим состоянием). */
  backTo?: string;
  /** Создать сценарий на месте (экран «Результат»); без него блок ведёт на экран «Результат» версии. */
  onCreateScenario?: (version: PackVersionRef) => void;
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

/** Лицензия и правила вклада: из ответа сервера (отказ без согласия) или из «Официальных паков». */
type LicenseInfo = {
  license: string;
  licenseUrl: string | null;
  contributingUrl: string | null;
};

const textField = (data: Record<string, unknown> | undefined, key: string) => {
  const value = data?.[key];
  return typeof value === "string" && value !== "" ? value : null;
};

const consentAsked = (error: unknown): LicenseInfo | null => {
  if (!(error instanceof ApiError) || error.code !== "license_consent_required")
    return null;
  const data = error.data as Record<string, unknown> | undefined;
  return {
    license: textField(data, "license") ?? "",
    licenseUrl: textField(data, "license_url"),
    contributingUrl: textField(data, "contributing_url"),
  };
};

/** Согласие перед первой отправкой в официальные паки (template-studio.md, 4.7). */
const LicenseConsent = ({
  info,
  checked,
  onChange,
}: {
  info: LicenseInfo;
  checked: boolean;
  onChange: (value: boolean) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const uid = useId();
  return (
    <div className="flex flex-col" style={{ gap: "0.375rem" }}>
      <label
        className="ps-choice"
        htmlFor={`${uid}-license`}
        data-testid="git-propose-license"
      >
        <input
          id={`${uid}-license`}
          type="checkbox"
          checked={checked}
          onChange={(e) => {
            onChange(e.target.checked);
          }}
          style={{ accentColor: "var(--accent)" }}
          data-testid="git-propose-license-accept"
        />
        <span className="ps-choice-text">
          <span>
            {t("git.official.consent", {
              license: info.license || t("git.official.repoLicense"),
            })}
          </span>
          <span className="ps-choice-hint">
            {t("git.official.consentHint")}
          </span>
        </span>
      </label>
      <span
        className="ps-choice-hint"
        style={{ display: "flex", gap: "0.75rem" }}
      >
        {info.licenseUrl && (
          <a href={info.licenseUrl} target="_blank" rel="noopener noreferrer">
            {t("git.official.license")}
          </a>
        )}
        {info.contributingUrl && (
          <a
            href={info.contributingUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("git.official.rules")}
          </a>
        )}
      </span>
    </div>
  );
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
      {result.git.workspace.official === true && (
        <p className="ps-dialog-text" data-testid="git-propose-release-hint">
          {t("git.official.afterMerge")}
        </p>
      )}
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
  version = null,
  backTo,
  onCreateScenario,
}: ProposeDialogProps) => {
  const { t } = useTranslation("packStudio");
  const propose = useProposePack(git.workspace.id);
  const [step, setStep] = useState<Step>({ kind: "form" });
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [forkMode, setForkMode] = useState<ForkMode>("url");
  const [forkUrl, setForkUrl] = useState("");
  const [accepted, setAccepted] = useState(false);
  // «До и после» (срез F10): отчёт блока, отметка «я знаю» и включение сводки в описание.
  const [impact, setImpact] = useState<ImpactReport | null>(null);
  const [ack, setAck] = useState(false);
  const [includeSummary, setIncludeSummary] = useState(true);
  const uid = useId();
  const word = prWord(git.provider);
  const ws = git.workspace;
  const isOfficial = ws.official === true;
  const official = usePackOfficial(isOpen && isOfficial);
  const repo = official.data?.repo;
  const asked = consentAsked(propose.error);
  // Согласие спрашивается до первой отправки и ещё раз, если сервер о нём попросил.
  const consentInfo: LicenseInfo | null =
    asked ??
    (isOfficial && !ws.license_accepted_at
      ? {
          license: repo?.license ?? "",
          licenseUrl: repo?.license_url ?? null,
          contributingUrl: repo?.contributing_url ?? null,
        }
      : null);

  const { versions, extra } = useMemo(
    () => impactVersions(git.changed, version),
    [git.changed, version],
  );
  const hasImpact = versions.length > 0;
  // Расчёт идёт, пока блок не отчитался или отчитался «считаю»; ничего не посчитано: отметки нет.
  const impactPending = hasImpact && (impact === null || impact.pending);
  const needsAck = hasImpact && impact?.needsAck === true;
  const onImpactFail = useCallback(() => {
    setImpact({ pending: false, needsAck: false, summary: "" });
  }, []);

  const reset = () => {
    propose.reset();
    setImpact(null);
    setAck(false);
    setIncludeSummary(true);
    setStep({ kind: "form" });
    setTitle("");
    setDescription("");
    setMessage("");
    setForkMode("url");
    setForkUrl("");
    setAccepted(false);
  };
  const close = () => {
    if (propose.isPending) return;
    reset();
    onClose();
  };

  const send = (fork: PackForkChoice | null) => {
    const summary =
      includeSummary && impact !== null && impact.summary !== ""
        ? impact.summary
        : null;
    const body = [trimmed(description), summary]
      .filter((part): part is string => part !== null)
      .join("\n\n");
    propose.mutate(
      {
        title: trimmed(title),
        description: body === "" ? null : body,
        message: git.dirty ? trimmed(message) : null,
        ...(fork ? { fork } : {}),
        ...(consentInfo && accepted ? { accept_license: true } : {}),
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
    error && !forkRequired(error) && !lintFailure(error) && !asked
      ? error
      : null;
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
          <Notice
            tone="err"
            role="alert"
            text={<PackErrorText error={shownError} />}
          />
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
        {hasImpact && (
          <div
            className="flex flex-col"
            style={{ gap: "0.5rem" }}
            data-testid="git-propose-impact"
          >
            <ImpactSlot
              workspaceId={ws.id}
              versions={versions}
              onReport={setImpact}
              onFail={onImpactFail}
              onLeave={close}
              backTo={backTo}
              onCreateScenario={
                onCreateScenario
                  ? (v) => {
                      close();
                      onCreateScenario(v);
                    }
                  : undefined
              }
            />
            {extra > 0 && (
              <p className="ps-dialog-text">
                {t("git.propose.impact.extra", { count: extra })}
              </p>
            )}
            {impactPending && (
              <p
                className="ps-dialog-text"
                role="status"
                data-testid="git-propose-impact-waiting"
              >
                {t("git.propose.impact.waiting")}
              </p>
            )}
            {needsAck && (
              <label
                className="ps-choice"
                htmlFor={`${uid}-ack`}
                data-testid="git-propose-ack"
              >
                <input
                  id={`${uid}-ack`}
                  type="checkbox"
                  checked={ack}
                  onChange={(e) => {
                    setAck(e.target.checked);
                  }}
                  style={{ accentColor: "var(--accent)" }}
                  data-testid="git-propose-ack-input"
                />
                <span className="ps-choice-text">
                  <span>{t("git.propose.impact.ack")}</span>
                  <span className="ps-choice-hint">
                    {t("git.propose.impact.ackHint")}
                  </span>
                </span>
              </label>
            )}
            {impact !== null && impact.summary !== "" && (
              <label
                className="ps-choice"
                htmlFor={`${uid}-summary`}
                data-testid="git-propose-summary"
              >
                <input
                  id={`${uid}-summary`}
                  type="checkbox"
                  checked={includeSummary}
                  onChange={(e) => {
                    setIncludeSummary(e.target.checked);
                  }}
                  style={{ accentColor: "var(--accent)" }}
                  data-testid="git-propose-summary-input"
                />
                <span className="ps-choice-text">
                  <span>{t("git.propose.impact.include")}</span>
                  <span className="ps-choice-hint">
                    {t("git.propose.impact.includeHint")}
                  </span>
                </span>
              </label>
            )}
          </div>
        )}
        {consentInfo && (
          <LicenseConsent
            info={consentInfo}
            checked={accepted}
            onChange={setAccepted}
          />
        )}
        {shownError !== null && (
          <Notice
            tone="err"
            role="alert"
            text={<PackErrorText error={shownError} />}
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
          disabled={
            propose.isPending ||
            (consentInfo !== null && !accepted) ||
            impactPending ||
            (needsAck && !ack)
          }
          onClick={() => {
            send(null);
          }}
          data-testid="git-propose-submit"
          data-impact={needsAck ? "warn" : undefined}
        >
          {propose.isPending
            ? t("git.propose.sending")
            : needsAck
              ? t("git.propose.impact.anyway")
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
