import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Modal, Section, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { LocalInstance } from "@entities/session";
import {
  useInstallJob,
  useRefreshRunners,
  useRemoveLocalInstance,
  useUpgradeLocalInstance,
} from "../api/opsQueries";
import { failureKey } from "../lib/failure";
import { InstallProgress } from "./InstallRunnerDialog";
import { ConfirmDialog } from "./RunnerDialogs";

/**
 * «Обновить раннер»: подтверждение с тем, что сохранится и что будет с
 * идущими сборками, затем ход по шагам (образ, манифест, перезапуск, связь).
 */
export const RunnerUpgradeDialog = ({
  instance,
  onClose,
}: {
  instance: LocalInstance | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  const upgrade = useUpgradeLocalInstance();
  const refresh = useRefreshRunners();
  const [jobId, setJobId] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const job = useInstallJob(jobId);
  const current = job.data;
  const finished = current !== undefined && current.state !== "running";
  const state = current?.state;

  // Версия и состояние раннера в таблице меняются только после перезапуска.
  useEffect(() => {
    if (state === "succeeded" || state === "failed") refresh();
  }, [state, refresh]);

  const close = () => {
    setJobId(null);
    setFailure(null);
    upgrade.reset();
    onClose();
  };
  const run = () => {
    if (!instance) return;
    setFailure(null);
    setJobId(null);
    upgrade.mutate(
      { target: instance.target, name: instance.name },
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

  const name = instance?.name ?? "";
  const to = instance?.studio_version ?? "";
  const reconnect = current?.steps.find((s) => s.key === "reconnect");

  return (
    <Modal
      isOpen={instance !== null}
      onClose={() => {
        if (jobId === null || finished) close();
      }}
      title={t("upgrade.title", { name })}
      width={560}
    >
      {instance && (
        <div
          className="flex flex-col"
          style={{ gap: "0.75rem", fontSize: "0.8125rem" }}
          data-testid="upgrade-dialog"
        >
          {jobId === null ? (
            <>
              <p style={{ margin: 0 }} data-testid="upgrade-versions">
                {instance.runner_version === null
                  ? t("upgrade.versionsUnknown", { to })
                  : instance.outdated
                    ? t("upgrade.versions", {
                        from: instance.runner_version,
                        to,
                      })
                    : t("upgrade.same", { to })}
              </p>
              <p style={{ margin: 0 }}>{t("upgrade.keeps")}</p>
              <p style={{ margin: 0 }}>{t(`upgrade.how.${instance.target}`)}</p>
              <p style={{ margin: 0 }} data-testid="upgrade-restart">
                {t("upgrade.restart")}
              </p>
              {failure && (
                <div data-testid="upgrade-start-failure">
                  <Notice
                    tone="err"
                    role="alert"
                    text={
                      failure === "install_busy"
                        ? t("upgrade.busy")
                        : t(failureKey(failure))
                    }
                  />
                </div>
              )}
              <div
                className="flex items-center"
                style={{ gap: "0.5rem", justifyContent: "flex-end" }}
              >
                <Button type="button" variant="ghost" onClick={close}>
                  {t("adminOps:cancel")}
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  disabled={upgrade.isPending}
                  onClick={run}
                  data-testid="upgrade-confirm"
                >
                  {t("upgrade.confirm")}
                </Button>
              </div>
            </>
          ) : (
            <>
              {current ? (
                <>
                  <p style={{ margin: 0 }}>
                    {t("upgrade.progress", { name: current.name })}
                  </p>
                  <InstallProgress job={current} />
                  {current.state === "succeeded" && (
                    <div data-testid="upgrade-success">
                      <Notice
                        tone="info"
                        role="status"
                        text={
                          reconnect?.state === "skipped"
                            ? t("upgrade.succeededNoRunner")
                            : t("upgrade.succeeded", {
                                version: reconnect?.detail || to,
                              })
                        }
                      />
                    </div>
                  )}
                  {current.state === "failed" && (
                    <div data-testid="upgrade-failed">
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
                {current?.state === "failed" && (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={run}
                    data-testid="upgrade-retry"
                  >
                    {t("retry")}
                  </Button>
                )}
                <Button
                  type="button"
                  variant={finished ? "ghost" : "primary"}
                  disabled={!finished}
                  onClick={close}
                  data-testid="upgrade-done"
                >
                  {t("done")}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </Modal>
  );
};

/** «Удалить установку»: что именно уберёт Студия и что останется. */
export const RemoveInstallDialog = ({
  instance,
  onClose,
}: {
  instance: LocalInstance | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  const remove = useRemoveLocalInstance();
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <ConfirmDialog
      isOpen={instance !== null}
      title={t("instances.removeTitle", { name: instance?.name ?? "" })}
      body={
        instance
          ? t(
              `instances.removeBody.${instance.target}${instance.runner_id ? "" : "Orphan"}`,
            )
          : ""
      }
      confirmLabel={t("instances.removeConfirm")}
      danger
      pending={remove.isPending}
      failure={failed ? { code: failed } : null}
      testId="install-remove-dialog"
      onClose={() => {
        setFailed(null);
        remove.reset();
        onClose();
      }}
      onConfirm={() => {
        if (!instance) return;
        setFailed(null);
        remove.mutate(
          { target: instance.target, name: instance.name },
          {
            onSuccess: () => {
              onClose();
            },
            onError: (error) => {
              setFailed(failureCode(error));
            },
          },
        );
      }}
    />
  );
};

/**
 * Установки из админки, чьего раннера нет в таблице: отозван, ещё не
 * подключился или не может подключиться (например, Deployment падает).
 */
export const InstallsWithoutRunner = ({
  instances,
  onRemove,
}: {
  instances: readonly LocalInstance[];
  onRemove: (instance: LocalInstance) => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  if (instances.length === 0) return null;
  return (
    <Section
      title={t("instances.title")}
      description={t("instances.lead")}
      testId="install-orphans"
    >
      <ul
        className="flex flex-col"
        style={{ gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}
      >
        {instances.map((instance) => (
          <li
            key={`${instance.target}/${instance.name}`}
            className="flex items-center"
            style={{ gap: "0.5rem", flexWrap: "wrap", fontSize: "0.8125rem" }}
            data-testid={`install-instance-${instance.name}`}
          >
            <span
              style={{ flex: 1, minWidth: "10rem", wordBreak: "break-all" }}
            >
              <span style={{ fontWeight: 600 }}>{instance.name}</span>
              <span className="form-hint">
                {" "}
                {t("instances.facts", {
                  target: t(`target.${instance.target}`),
                  state: instance.state,
                  image: instance.image,
                })}
              </span>
            </span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                onRemove(instance);
              }}
              data-testid={`install-instance-${instance.name}-remove`}
            >
              {t("instances.remove")}
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  );
};
