import { useTranslation } from "react-i18next";
import type { Probe } from "@entities/git-remote";
import type { GitContents } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { formatSize } from "../lib/formatSize";
import { issueCopyOf, type IssueAction } from "../model/issueCopy";
import type { CheckIssue, CheckOutcome } from "../model/probeOutcome";
import { ConfirmCheck } from "./ConfirmCheck";
import { Btn, Facts, ResultFrame } from "./ResultFrame";

export type ProbeResultHandlers = {
  onConnect: (sync: boolean) => void;
  onAdopt: () => void;
  onRetry: () => void;
  onBackToRepo: () => void;
  onBackToAccess: () => void;
  onReviewHostKey: () => void;
  onPickBranch: (branch: string) => void;
  onClose: () => void;
  onCloneInstead?: (() => void) | undefined;
};

export type IssueHandlers = Pick<
  ProbeResultHandlers,
  | "onRetry"
  | "onBackToRepo"
  | "onBackToAccess"
  | "onReviewHostKey"
  | "onPickBranch"
  | "onClose"
>;

export type ProbeResultCardProps = ProbeResultHandlers & {
  outcome: CheckOutcome;
  probe: Probe | null;
  contents: GitContents | undefined;
  fixing: boolean;
  isConnecting: boolean;
  adoptConfirmed: boolean;
  onAdoptConfirmedChange: (value: boolean) => void;
};

export const ProbeIssueCard = ({
  issue,
  probe,
  fixing,
  handlers,
}: {
  issue: CheckIssue;
  probe: Probe | null;
  fixing: boolean;
  handlers: IssueHandlers;
}) => {
  const { t, i18n } = useTranslation("gitRemote");
  const base = issueCopyOf(issue.code);
  // Адрес подключённого проекта не меняется: «Изменить адрес» там не предлагаем.
  const actions = base.actions.filter(
    (action) => !(fixing && action === "back_to_repo"),
  );
  const copy = {
    tone: base.tone,
    actions: actions.length > 0 ? actions : (["retry"] as IssueAction[]),
  };
  const ownTitle = `issue.${issue.code}.title`;
  const ownHint = `issue.${issue.code}.hint`;
  const title = i18n.exists(`gitRemote:${ownTitle}`)
    ? t(ownTitle)
    : t("issue.generic.title");
  const hint = i18n.exists(`gitRemote:${ownHint}`)
    ? t(ownHint)
    : t(`errors:code.${issue.code}`, { defaultValue: issue.detail });
  const branches =
    issue.code === "branch_missing" ? (probe?.branches ?? []) : [];

  const label = (action: IssueAction): string =>
    action === "back_to_access" && fixing
      ? t("issue.actions.updateAccess")
      : t(`issue.actions.${action}`);
  const run = (action: IssueAction): void => {
    switch (action) {
      case "retry":
        handlers.onRetry();
        return;
      case "back_to_repo":
        handlers.onBackToRepo();
        return;
      case "back_to_access":
        handlers.onBackToAccess();
        return;
      case "review_host_key":
        handlers.onReviewHostKey();
        return;
      case "close":
        handlers.onClose();
    }
  };

  return (
    <ResultFrame
      tone={copy.tone}
      title={title}
      testId={`probe-result-${issue.code}`}
      role="alert"
      actions={copy.actions.map((action, index) => (
        <Btn
          key={action}
          primary={index === 0}
          onClick={() => {
            run(action);
          }}
        >
          {label(action)}
        </Btn>
      ))}
    >
      <p style={{ margin: 0 }}>{hint}</p>
      {branches.length > 0 && (
        <div>
          <div className="dim" style={{ fontSize: 11.5, marginBottom: 5 }}>
            {t("issue.branch_missing.available")}
          </div>
          <div className="flex" style={{ gap: 6, flexWrap: "wrap" }}>
            {branches.map((branch) => (
              <button
                key={branch}
                type="button"
                className="chip accent"
                style={{ cursor: "pointer", height: 24 }}
                onClick={() => {
                  handlers.onPickBranch(branch);
                }}
              >
                {branch}
              </button>
            ))}
          </div>
        </div>
      )}
      {issue.detail !== "" && (
        <details className="sync-details">
          <summary>{t("issue.details")}</summary>
          <pre
            className="mono"
            style={{
              margin: "6px 0 0",
              fontSize: 11,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "var(--fg-2)",
            }}
          >
            {issue.detail}
          </pre>
        </details>
      )}
    </ResultFrame>
  );
};

// Итог проверки адреса: что нашли и что можно делать дальше. Отказы разобраны по
// кодам, у каждого понятная причина и действие, которое её исправляет.
export const ProbeResultCard = ({
  outcome,
  probe,
  contents,
  fixing,
  isConnecting,
  adoptConfirmed,
  onAdoptConfirmedChange,
  ...handlers
}: ProbeResultCardProps) => {
  const { t } = useTranslation("gitRemote");

  if (outcome.kind === "error") {
    return (
      <ProbeIssueCard
        issue={outcome.issue}
        probe={probe}
        fixing={fixing}
        handlers={handlers}
      />
    );
  }

  if (outcome.kind === "not_studio") {
    return (
      <ResultFrame
        tone="err"
        role="alert"
        title={t("result.notStudio.title")}
        testId="probe-result-not_studio"
        actions={
          <Btn primary onClick={handlers.onBackToRepo}>
            {t("result.chooseAnother")}
          </Btn>
        }
      >
        <p style={{ margin: 0 }}>{t("result.notStudio.text")}</p>
      </ResultFrame>
    );
  }

  if (outcome.kind === "other_project") {
    return (
      <ResultFrame
        tone="err"
        role="alert"
        title={t("result.otherProject.title")}
        testId="probe-result-other_project"
        actions={
          <>
            {handlers.onCloneInstead && (
              <Btn primary onClick={handlers.onCloneInstead}>
                {t("result.cloneInstead")}
              </Btn>
            )}
            <Btn
              primary={!handlers.onCloneInstead}
              onClick={handlers.onBackToRepo}
            >
              {t("result.chooseAnother")}
            </Btn>
          </>
        }
      >
        <p style={{ margin: 0 }}>
          {probe?.project
            ? t("result.otherProject.textNamed", { name: probe.project.name })
            : t("result.otherProject.text")}
        </p>
        <p className="dim" style={{ margin: 0 }}>
          {t("result.otherProject.hint")}
        </p>
      </ResultFrame>
    );
  }

  if (outcome.kind === "unrelated") {
    return (
      <ResultFrame
        tone="warn"
        title={t("result.unrelated.title")}
        testId="probe-result-unrelated"
        actions={
          <>
            <Btn
              primary
              onClick={handlers.onAdopt}
              disabled={!adoptConfirmed}
              busy={isConnecting}
            >
              {t("result.unrelated.adopt")}
            </Btn>
            <Btn onClick={handlers.onBackToRepo} disabled={isConnecting}>
              {t("result.chooseAnother")}
            </Btn>
          </>
        }
      >
        <p style={{ margin: 0 }}>{t("result.unrelated.text")}</p>
        <ConfirmCheck
          checked={adoptConfirmed}
          onChange={onAdoptConfirmedChange}
          testId="adopt-confirm"
        >
          {t("result.unrelated.confirm")}
        </ConfirmCheck>
      </ResultFrame>
    );
  }

  // --- можно подключать -------------------------------------------------------
  const project = probe?.project ?? null;
  const facts: [string, string][] = [];
  if (project) {
    facts.push([t("result.facts.project"), project.name]);
    facts.push([
      t("result.facts.template"),
      `${project.template_id} ${project.template_version}`,
    ]);
    facts.push([t("result.facts.authors"), String(project.authors_count)]);
  }
  const branchName = probe?.default_branch;
  if (branchName) facts.push([t("result.facts.branch"), branchName]);

  const title = fixing
    ? t("result.fix.title")
    : t(`result.ready.${outcome.variant}.title`);
  const text = fixing
    ? t("result.fix.text")
    : outcome.variant === "empty" && contents
      ? t("result.ready.empty.textWithContents", {
          files: t("contents.files", { count: contents.files }),
          size: formatSize(contents.bytes),
          versions: t("contents.versions", { count: contents.commits }),
        })
      : t(`result.ready.${outcome.variant}.text`);

  return (
    <ResultFrame
      tone="ok"
      role="status"
      title={title}
      testId={`probe-result-ready-${outcome.variant}`}
      actions={
        fixing ? (
          <Btn
            primary
            onClick={() => {
              handlers.onConnect(false);
            }}
            busy={isConnecting}
          >
            {t("result.fix.save")}
          </Btn>
        ) : (
          <>
            <Btn
              primary
              onClick={() => {
                handlers.onConnect(true);
              }}
              busy={isConnecting}
            >
              {t("result.connectAndSync")}
            </Btn>
            <Btn
              onClick={() => {
                handlers.onConnect(false);
              }}
              disabled={isConnecting}
            >
              {t("result.connectOnly")}
            </Btn>
          </>
        )
      }
    >
      <p style={{ margin: 0 }}>{text}</p>
      {facts.length > 0 && <Facts items={facts} />}
      {outcome.warnings.includes("schema_newer") && (
        <Notice
          tone="warn"
          role="status"
          text={
            probe?.required_studio
              ? `${t("result.warn.schemaNewer")} ${t("result.warn.schemaNewerVersion", { version: probe.required_studio })}`
              : t("result.warn.schemaNewer")
          }
        />
      )}
      {outcome.warnings.includes("template_missing") && (
        <Notice
          tone="warn"
          role="status"
          text={t("result.warn.templateMissing")}
        />
      )}
    </ResultFrame>
  );
};
