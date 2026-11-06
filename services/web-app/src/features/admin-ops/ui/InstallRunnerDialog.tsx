import { useState } from "react";
import { Check, Circle, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  InstallCapability,
  InstallJob,
  LocalInstance,
} from "@entities/session";
import {
  useInstallJob,
  useLocalInstallCapabilities,
  useLocalInstances,
  useRemoveLocalInstance,
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
  const { t } = useTranslation("adminRunners");
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
          <span>{t(`install.step.${step.key}`)}</span>
          <span className="sr-only">
            {t(`install.stepState.${step.state}`)}
          </span>
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
  const { t } = useTranslation("adminRunners");
  return (
    <Row
      title={t(`install.local.${target}.title`)}
      lead={t(`install.local.${target}.lead`)}
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
          {t("install.local.start")}
        </Button>
      ) : (
        <p
          className="form-hint"
          style={{ margin: 0 }}
          data-testid={`install-local-${target}-unavailable`}
        >
          {t(`install.reason.${target}.${capability.reason ?? "disabled"}`)}
        </p>
      )}
    </Row>
  );
};

const InstanceRow = ({
  instance,
  onRemove,
  pending,
}: {
  instance: LocalInstance;
  onRemove: (instance: LocalInstance) => void;
  pending: boolean;
}) => {
  const { t } = useTranslation("adminRunners");
  const [sure, setSure] = useState(false);
  return (
    <li
      className="flex items-center"
      style={{ gap: "0.5rem", flexWrap: "wrap", fontSize: "0.8125rem" }}
      data-testid={`install-instance-${instance.name}`}
    >
      <span style={{ flex: 1, minWidth: "10rem", wordBreak: "break-all" }}>
        {instance.name}
        <span className="form-hint">
          {" "}
          {t(`install.target.${instance.target}`)}, {instance.state}
        </span>
      </span>
      {sure ? (
        <>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setSure(false);
            }}
          >
            {t("adminOps:cancel")}
          </Button>
          <button
            type="button"
            className="btn danger"
            disabled={pending}
            onClick={() => {
              onRemove(instance);
            }}
            data-testid={`install-instance-${instance.name}-confirm`}
          >
            {t("install.instances.removeConfirm")}
          </button>
        </>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setSure(true);
          }}
          data-testid={`install-instance-${instance.name}-remove`}
        >
          {t("install.instances.remove")}
        </Button>
      )}
    </li>
  );
};

/**
 * «Установить раннер»: на этой же машине (docker рядом, Deployment в кластере) с ходом по шагам
 * и список поставленных отсюда; для другой машины ведёт к команде у токена.
 */
export const InstallRunnerDialog = ({
  isOpen,
  onClose,
  onOpenCommand,
}: {
  isOpen: boolean;
  onClose: () => void;
  onOpenCommand: () => void;
}) => {
  const { t } = useTranslation("adminRunners");
  const capabilities = useLocalInstallCapabilities(isOpen);
  const instances = useLocalInstances(isOpen);
  const start = useStartLocalInstall();
  const remove = useRemoveLocalInstance();
  const [name, setName] = useState("");
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
    onClose();
  };
  const run = (target: Target) => {
    setFailure(null);
    setLast(target);
    start.mutate(
      { target, body: { name: name.trim(), concurrency: 1 } },
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
      title={t("install.title")}
      description={t("install.lead")}
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
                label={t("install.name")}
                hint={t("install.nameHint")}
                value={name}
                maxLength={40}
                autoComplete="off"
                onChange={(event) => {
                  setName(event.target.value);
                }}
                data-testid="install-name"
              />
              <span className="form-label">{t("install.local.heading")}</span>
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
                  text={t("install.capabilitiesFailed")}
                />
              )}
              {failure && (
                <div data-testid="install-start-failure">
                  <Notice
                    tone="err"
                    role="alert"
                    text={
                      failure === "install_busy"
                        ? t("install.busy")
                        : t(failureKey(failure))
                    }
                  />
                </div>
              )}
              <Row
                title={t("install.command.title")}
                lead={t("install.command.lead")}
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
                  {t("install.command.open")}
                </Button>
              </Row>
              {instances.data && instances.data.length > 0 && (
                <div className="flex flex-col" style={{ gap: "0.375rem" }}>
                  <span className="form-label">
                    {t("install.instances.title")}
                  </span>
                  <ul
                    className="flex flex-col"
                    style={{
                      gap: "0.375rem",
                      margin: 0,
                      padding: 0,
                      listStyle: "none",
                    }}
                    data-testid="install-instances"
                  >
                    {instances.data.map((instance) => (
                      <InstanceRow
                        key={`${instance.target}/${instance.name}`}
                        instance={instance}
                        pending={remove.isPending}
                        onRemove={(item) => {
                          remove.mutate({
                            target: item.target,
                            name: item.name,
                          });
                        }}
                      />
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col" style={{ gap: "0.75rem" }}>
              {current ? (
                <>
                  <p style={{ margin: 0, fontSize: "0.8125rem" }}>
                    {t("install.progress", { name: current.name })}
                  </p>
                  <InstallProgress job={current} />
                  {current.state === "succeeded" && (
                    <div data-testid="install-success">
                      <Notice
                        tone="info"
                        role="status"
                        text={t("install.succeeded")}
                      />
                    </div>
                  )}
                  {current.state === "failed" && (
                    <div data-testid="install-failed">
                      <Notice
                        tone="err"
                        role="alert"
                        text={t(
                          `install.error.${current.error_code ?? "unexpected"}`,
                          {
                            defaultValue: t("install.error.unexpected"),
                          },
                        )}
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
                    {t("install.retry")}
                  </Button>
                )}
                <Button
                  type="button"
                  variant={finished ? "ghost" : "primary"}
                  disabled={!finished}
                  onClick={close}
                  data-testid="install-done"
                >
                  {t("install.done")}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};
