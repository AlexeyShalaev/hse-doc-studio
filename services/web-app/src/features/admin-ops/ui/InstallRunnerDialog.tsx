import { useState } from "react";
import { Check, Circle, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { InstallCapability, InstallJob } from "@entities/session";
import {
  useInstallJob,
  useLocalInstallCapabilities,
  useStartLocalInstall,
} from "../api/opsQueries";
import { failureKey } from "../lib/failure";

type Target = "docker" | "kubernetes";

const STEP_ICON = {
  pending: <Circle size="0.875rem" aria-hidden="true" />,
  running: (
    <Loader2 size="0.875rem" className="animate-spin" aria-hidden="true" />
  ),
  done: <Check size="0.875rem" aria-hidden="true" />,
  failed: <X size="0.875rem" aria-hidden="true" />,
  skipped: <Circle size="0.875rem" aria-hidden="true" />,
} as const;

/** Шаги установки: что сделано, что идёт, где упало. */
export const InstallProgress = ({ job }: { job: InstallJob }) => {
  const { t } = useTranslation("adminRunnerInstall");
  return (
    <ol
      className="flex flex-col"
      style={{ gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}
      data-testid="install-steps"
    >
      {job.steps.map((step) => (
        <li
          key={step.key}
          className="flex items-center"
          style={{
            gap: "0.5rem",
            fontSize: "0.8125rem",
            color: step.state === "pending" ? "var(--fg-3)" : "var(--fg-1)",
          }}
          data-testid={`install-step-${step.key}`}
          data-state={step.state}
        >
          <span aria-hidden="true" style={{ display: "inline-flex" }}>
            {STEP_ICON[step.state]}
          </span>
          <span>{t(`step.${step.key}`)}</span>
          <span className="sr-only">{t(`stepState.${step.state}`)}</span>
        </li>
      ))}
    </ol>
  );
};

const Row = ({
  title,
  lead,
  children,
  testId,
}: {
  title: string;
  lead: string;
  children: React.ReactNode;
  testId: string;
}) => (
  <div
    className="flex flex-col"
    style={{
      gap: "0.375rem",
      padding: "0.75rem",
      border: "1px solid var(--border)",
      borderRadius: "var(--r-2)",
    }}
    data-testid={testId}
  >
    <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{title}</span>
    <span className="form-hint">{lead}</span>
    <div>{children}</div>
  </div>
);

type LimitsForm = {
  runner_cpu: string;
  runner_memory: string;
  build_cpu: string;
  build_memory: string;
};
const NO_LIMITS: LimitsForm = {
  runner_cpu: "",
  runner_memory: "",
  build_cpu: "",
  build_memory: "",
};
const LIMIT_FIELDS = [
  "build_memory",
  "build_cpu",
  "runner_memory",
  "runner_cpu",
] as const;

/** Только непустые поля: пусто значит умолчание Helm. */
const limitsBody = (form: LimitsForm) => {
  const filled = Object.fromEntries(
    LIMIT_FIELDS.map((key) => [key, form[key].trim()]).filter(
      ([, value]) => value !== "",
    ),
  ) as Partial<LimitsForm>;
  return Object.keys(filled).length > 0 ? { resources: filled } : {};
};

/** Лимиты CPU и памяти для установки в кластер: подсказка с границами, значения проверяет бэкенд. */
const LimitsFields = ({
  value,
  onChange,
}: {
  value: LimitsForm;
  onChange: (next: LimitsForm) => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  return (
    <details data-testid="install-limits">
      <summary className="form-label" style={{ cursor: "pointer" }}>
        {t("limits.title")}
      </summary>
      <div
        className="flex flex-col"
        style={{ gap: "0.5rem", marginTop: "0.5rem" }}
      >
        <span className="form-hint">{t("limits.hint")}</span>
        {LIMIT_FIELDS.map((key) => (
          <Input
            key={key}
            label={t(`limits.${key}`)}
            value={value[key]}
            maxLength={12}
            autoComplete="off"
            placeholder={t(`limits.placeholder.${key}`)}
            onChange={(event) => {
              onChange({ ...value, [key]: event.target.value });
            }}
            data-testid={`install-limit-${key}`}
          />
        ))}
      </div>
    </details>
  );
};

const TargetRow = ({
  target,
  capability,
  onInstall,
  disabled,
}: {
  target: Target;
  capability: InstallCapability;
  onInstall: (target: Target) => void;
  disabled: boolean;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  return (
    <Row
      title={t(`local.${target}.title`)}
      lead={t(`local.${target}.lead`)}
      testId={`install-local-${target}`}
    >
      {capability.available ? (
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={disabled}
          onClick={() => {
            onInstall(target);
          }}
          data-testid={`install-local-${target}-start`}
        >
          {t("local.start")}
        </Button>
      ) : (
        <p
          className="form-hint"
          style={{ margin: 0 }}
          data-testid={`install-local-${target}-unavailable`}
        >
          {t(`reason.${target}.${capability.reason ?? "disabled"}`)}
        </p>
      )}
    </Row>
  );
};

/**
 * «Установить раннер»: на этой же машине (docker рядом, Deployment в кластере) с ходом по шагам;
 * для другой машины ведёт к команде у токена. Поставленными отсюда управляют на самой странице:
 * в меню строки раннера и в блоке «Установки без раннера».
 */
export const InstallRunnerDialog = ({
  isOpen,
  onClose,
  onOpenCommand,
  onOpenSsh,
}: {
  isOpen: boolean;
  onClose: () => void;
  onOpenCommand: () => void;
  onOpenSsh?: () => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  const capabilities = useLocalInstallCapabilities(isOpen);
  const start = useStartLocalInstall();
  const [name, setName] = useState("");
  const [limits, setLimits] = useState<LimitsForm>(NO_LIMITS);
  const [jobId, setJobId] = useState<string | null>(null);
  const [last, setLast] = useState<Target | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const job = useInstallJob(jobId);

  const reset = () => {
    setJobId(null);
    setFailure(null);
    start.reset();
  };
  const close = () => {
    reset();
    setName("");
    setLimits(NO_LIMITS);
    onClose();
  };
  const run = (target: Target) => {
    setFailure(null);
    setLast(target);
    start.mutate(
      {
        target,
        body: {
          name: name.trim(),
          concurrency: 1,
          ...(target === "kubernetes" ? limitsBody(limits) : {}),
        },
      },
      {
        onSuccess: (created) => {
          setJobId(created.id);
        },
        onError: (error) => {
          setFailure(failureCode(error));
        },
      },
    );
  };

  const current = job.data;
  const finished = current !== undefined && current.state !== "running";
  const busy = start.isPending || (current !== undefined && !finished);

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("title")}
      description={t("lead")}
      width={600}
    >
      {isOpen && (
        <div
          className="flex flex-col"
          style={{ gap: "0.875rem" }}
          data-testid="install-dialog"
        >
          {jobId === null ? (
            <>
              <Input
                label={t("name")}
                hint={t("nameHint")}
                value={name}
                maxLength={40}
                autoComplete="off"
                onChange={(event) => {
                  setName(event.target.value);
                }}
                data-testid="install-name"
              />
              {capabilities.data?.kubernetes.available && (
                <LimitsFields value={limits} onChange={setLimits} />
              )}
              <span className="form-label">{t("local.heading")}</span>
              {capabilities.isPending ? (
                <Spinner size="sm" />
              ) : capabilities.data ? (
                <>
                  <TargetRow
                    target="docker"
                    capability={capabilities.data.docker}
                    onInstall={run}
                    disabled={busy}
                  />
                  <TargetRow
                    target="kubernetes"
                    capability={capabilities.data.kubernetes}
                    onInstall={run}
                    disabled={busy}
                  />
                </>
              ) : (
                <Notice
                  tone="err"
                  role="alert"
                  text={t("capabilitiesFailed")}
                />
              )}
              {failure && (
                <div data-testid="install-start-failure">
                  <Notice
                    tone="err"
                    role="alert"
                    text={
                      failure === "install_busy"
                        ? t("busy")
                        : failure === "invalid_resources"
                          ? t("limits.invalid")
                          : t(failureKey(failure))
                    }
                  />
                </div>
              )}
              {onOpenSsh && (
                <Row
                  title={t("ssh.rowTitle")}
                  lead={t("ssh.rowLead")}
                  testId="install-ssh"
                >
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      close();
                      onOpenSsh();
                    }}
                    data-testid="install-ssh-open"
                  >
                    {t("ssh.open")}
                  </Button>
                </Row>
              )}
              <Row
                title={t("command.title")}
                lead={t("command.lead")}
                testId="install-command"
              >
                <Button
                  type="button"
                  size="sm"
                  onClick={() => {
                    close();
                    onOpenCommand();
                  }}
                  data-testid="install-command-open"
                >
                  {t("command.open")}
                </Button>
              </Row>
            </>
          ) : (
            <div className="flex flex-col" style={{ gap: "0.75rem" }}>
              {current ? (
                <>
                  <p style={{ margin: 0, fontSize: "0.8125rem" }}>
                    {t("progress", { name: current.name })}
                  </p>
                  <InstallProgress job={current} />
                  {current.state === "succeeded" && (
                    <div data-testid="install-success">
                      <Notice tone="info" role="status" text={t("succeeded")} />
                    </div>
                  )}
                  {current.state === "failed" && (
                    <div data-testid="install-failed">
                      <Notice
                        tone="err"
                        role="alert"
                        text={t(`error.${current.error_code ?? "unexpected"}`, {
                          defaultValue: t("error.unexpected"),
                        })}
                      />
                      {current.error_detail && (
                        <pre
                          className="form-hint"
                          style={{
                            whiteSpace: "pre-wrap",
                            margin: "0.375rem 0 0",
                          }}
                        >
                          {current.error_detail}
                        </pre>
                      )}
                    </div>
                  )}
                </>
              ) : (
                <Spinner size="sm" />
              )}
              <div
                className="flex items-center"
                style={{ gap: "0.5rem", justifyContent: "flex-end" }}
              >
                {current?.state === "failed" && last !== null && (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={() => {
                      const target = last;
                      reset();
                      run(target);
                    }}
                    data-testid="install-retry"
                  >
                    {t("retry")}
                  </Button>
                )}
                <Button
                  type="button"
                  variant={finished ? "ghost" : "primary"}
                  disabled={!finished}
                  onClick={close}
                  data-testid="install-done"
                >
                  {t("done")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};
