import { useEffect, useState, type FormEvent } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ApiError, failureCode } from "@shared/api";
import { loadAdminNamespaces, reportIfChunkError } from "@shared/lib";
import type { AdminNamespace } from "@shared/lib";
import { Button, Input, Modal, Spinner, Textarea } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  ModelServerInstall,
  SavedSshCredential,
  SshPlan,
} from "@entities/session";
import {
  useInstallJob,
  useSshCapability,
  useSshConfirm,
  useSshCredentials,
  useSshDeleteCredential,
  useSshInstall,
  useSshProbe,
  useSshRunSaved,
} from "../api/opsQueries";
import { opsApi } from "../api/opsApi";
import { failureKey } from "../lib/failure";
import { InstallProgress } from "./InstallRunnerDialog";

type Stage = "form" | "fingerprint" | "plan" | "progress";
type AuthKind = "password" | "key";

type FormState = {
  host: string;
  port: string;
  username: string;
  authKind: AuthKind;
  password: string;
  privateKey: string;
  passphrase: string;
  sudo: boolean;
  save: boolean;
  label: string;
  name: string;
};

const EMPTY: FormState = {
  host: "",
  port: "22",
  username: "",
  authKind: "password",
  password: "",
  privateKey: "",
  passphrase: "",
  sudo: false,
  save: false,
  label: "",
  name: "",
};

const Field = ({ children }: { children: React.ReactNode }) => (
  <div className="flex flex-col" style={{ gap: "0.375rem" }}>
    {children}
  </div>
);

/** Сообщение об отказе: код каталога SSH, причина политики адреса либо общий отказ. */
const errorText = (t: TFunction, code: string, reason?: string): string => {
  if (code === "address_blocked") {
    return t("adminRunnerSsh:error.address_blocked", {
      reason: t(`adminRunnerSsh:blocked.${reason ?? "private"}`, {
        defaultValue: reason ?? "",
      }),
    });
  }
  const key = `adminRunnerSsh:error.${code}`;
  const text = t(key, { defaultValue: "" });
  return text !== "" ? text : t(failureKey(code));
};

const SavedList = ({
  items,
  busy,
  onRun,
  onDelete,
}: {
  items: SavedSshCredential[];
  busy: boolean;
  onRun: (item: SavedSshCredential, action: "update" | "reinstall") => void;
  onDelete: (item: SavedSshCredential) => void;
}) => {
  const { t } = useTranslation("adminRunnerInstall");
  const [confirm, setConfirm] = useState<string | null>(null);
  return (
    <div className="flex flex-col" style={{ gap: "0.5rem" }}>
      <span className="form-label">{t("adminRunnerSsh:saved.title")}</span>
      <p className="form-hint" style={{ margin: 0 }}>
        {t("adminRunnerSsh:saved.lead")}
      </p>
      <ul
        className="flex flex-col"
        style={{ gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}
        data-testid="ssh-saved"
      >
        {items.map((item) => (
          <li
            key={item.id}
            className="flex flex-col"
            style={{
              gap: "0.375rem",
              padding: "0.625rem",
              border: "1px solid var(--border)",
              borderRadius: "var(--r-2)",
              fontSize: "0.8125rem",
            }}
            data-testid={`ssh-saved-${item.id}`}
          >
            <span style={{ fontWeight: 600, wordBreak: "break-all" }}>
              {item.label}
            </span>
            <span className="form-hint" style={{ wordBreak: "break-all" }}>
              {item.username}@{item.host}:{item.port},{" "}
              {t(`adminRunnerSsh:saved.auth.${item.auth_kind}`)},{" "}
              {item.fingerprint}
            </span>
            <span className="form-hint">
              {t("adminRunnerSsh:saved.present")}
            </span>
            <div className="flex" style={{ gap: "0.375rem", flexWrap: "wrap" }}>
              <Button
                type="button"
                size="sm"
                variant="primary"
                disabled={busy}
                onClick={() => {
                  onRun(item, "update");
                }}
                data-testid={`ssh-saved-update-${item.id}`}
              >
                {t("adminRunnerSsh:saved.update")}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={busy}
                onClick={() => {
                  onRun(item, "reinstall");
                }}
                data-testid={`ssh-saved-reinstall-${item.id}`}
              >
                {t("adminRunnerSsh:saved.reinstall")}
              </Button>
              {confirm === item.id ? (
                <button
                  type="button"
                  className="btn danger"
                  onClick={() => {
                    setConfirm(null);
                    onDelete(item);
                  }}
                  data-testid={`ssh-saved-delete-confirm-${item.id}`}
                >
                  {t("adminRunnerSsh:saved.deleteConfirm")}
                </button>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setConfirm(item.id);
                  }}
                  data-testid={`ssh-saved-delete-${item.id}`}
                >
                  {t("adminRunnerSsh:saved.delete")}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

type SshInstallDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  /** Поставить сервер ИИ-модели вместо раннера: тот же вход, отпечаток и ход, другая полезная нагрузка. */
  modelServer?: ModelServerInstall | null;
};

/**
 * Пароль и ключ живут только в состоянии формы и уходят одним запросом; сервер не возвращает их никогда.
 */
const SshInstallDialogBody = ({
  isOpen,
  onClose,
  modelServer = null,
}: SshInstallDialogProps) => {
  const { t } = useTranslation("adminRunnerInstall");
  const capability = useSshCapability(isOpen);
  const saved = useSshCredentials(isOpen);
  const probe = useSshProbe();
  const confirm = useSshConfirm();
  const install = useSshInstall();
  const runSaved = useSshRunSaved();
  const del = useSshDeleteCredential();
  const [stage, setStage] = useState<Stage>("form");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [session, setSession] = useState<string | null>(null);
  const [hostKey, setHostKey] = useState<{
    key_type: string;
    fingerprint: string;
  } | null>(null);
  const [plan, setPlan] = useState<SshPlan | null>(null);
  const [installDocker, setInstallDocker] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useInstallJob(jobId);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };
  const fail = (e: unknown) => {
    const code = failureCode(e);
    const raw = e instanceof ApiError ? e.data?.reason : undefined;
    const reason = typeof raw === "string" ? raw : undefined;
    setError(errorText(t, code, reason));
  };
  const reset = () => {
    // Секреты стираются из состояния при любом выходе.
    setForm(EMPTY);
    setStage("form");
    setSession(null);
    setHostKey(null);
    setPlan(null);
    setInstallDocker(false);
    setJobId(null);
    setError(null);
    probe.reset();
    confirm.reset();
    install.reset();
    runSaved.reset();
  };
  const close = () => {
    if (session && stage !== "progress")
      void opsApi.sshCancel(session).catch(() => undefined);
    reset();
    onClose();
  };

  const port = Number(form.port);
  const valid =
    form.host.trim() !== "" &&
    form.username.trim() !== "" &&
    Number.isInteger(port) &&
    port >= 1 &&
    port <= 65535 &&
    (form.authKind === "password"
      ? form.password !== ""
      : form.privateKey.trim() !== "");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setError(null);
    probe.mutate(
      {
        host: form.host.trim(),
        port,
        username: form.username.trim(),
        auth_kind: form.authKind,
        password: form.authKind === "password" ? form.password : null,
        private_key: form.authKind === "key" ? form.privateKey : null,
        passphrase:
          form.authKind === "key" && form.passphrase !== ""
            ? form.passphrase
            : null,
        sudo: form.sudo,
        save_credentials: form.save,
        label: form.label.trim(),
      },
      {
        onSuccess: (result) => {
          setSession(result.session_id);
          setHostKey(result.host_key);
          setStage("fingerprint");
        },
        onError: fail,
      },
    );
  };

  const doConfirm = () => {
    if (!session || !hostKey) return;
    setError(null);
    confirm.mutate(
      { sessionId: session, fingerprint: hostKey.fingerprint },
      {
        onSuccess: (result) => {
          setPlan(result);
          setStage("plan");
        },
        onError: fail,
      },
    );
  };

  const startInstall = () => {
    if (!session) return;
    setError(null);
    install.mutate(
      {
        sessionId: session,
        body: {
          name: form.name.trim(),
          install_docker: installDocker,
          ...(modelServer ? { model_server: modelServer } : {}),
        },
      },
      {
        onSuccess: (created) => {
          setJobId(created.id);
          setStage("progress");
        },
        onError: fail,
      },
    );
  };

  const startSaved = (
    item: SavedSshCredential,
    action: "update" | "reinstall",
  ) => {
    setError(null);
    runSaved.mutate(
      { id: item.id, action },
      {
        onSuccess: (created) => {
          setJobId(created.id);
          setStage("progress");
        },
        onError: fail,
      },
    );
  };

  const current = job.data;
  const finished = current !== undefined && current.state !== "running";
  const needsDocker = plan?.plan.some((p) => p.action === "install_docker");
  const blocked = plan?.plan.find((p) => p.action === "blocked");
  const dockerOk = !needsDocker || installDocker;

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={
        modelServer
          ? t("adminModelServers:ssh.title")
          : t("adminRunnerSsh:title")
      }
      description={
        modelServer ? t("adminModelServers:ssh.lead") : t("adminRunnerSsh:lead")
      }
      width={640}
    >
      {isOpen && (
        <div
          className="flex flex-col"
          style={{ gap: "0.875rem" }}
          data-testid="ssh-dialog"
        >
          {error && (
            <div data-testid="ssh-error">
              <Notice tone="err" role="alert" text={error} />
            </div>
          )}

          {capability.data && !capability.data.enabled && (
            <Notice tone="info" text={t("adminRunnerSsh:disabled")} />
          )}

          {stage === "form" && capability.data?.enabled && (
            <>
              {!modelServer && saved.data && saved.data.length > 0 && (
                <SavedList
                  items={saved.data}
                  busy={runSaved.isPending}
                  onRun={startSaved}
                  onDelete={(item) => {
                    del.mutate(item.id);
                  }}
                />
              )}
              <form
                className="flex flex-col"
                style={{ gap: "0.75rem" }}
                noValidate
                autoComplete="off"
                onSubmit={submit}
                data-testid="ssh-form"
              >
                <div
                  className="grid"
                  style={{
                    gap: "0.75rem",
                    gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))",
                  }}
                >
                  <Input
                    label={t("adminRunnerSsh:host")}
                    value={form.host}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(e) => {
                      set("host", e.target.value);
                    }}
                    data-testid="ssh-host"
                  />
                  <Input
                    label={t("adminRunnerSsh:port")}
                    type="number"
                    min={1}
                    max={65535}
                    value={form.port}
                    onChange={(e) => {
                      set("port", e.target.value);
                    }}
                    data-testid="ssh-port"
                  />
                  <Input
                    label={t("adminRunnerSsh:username")}
                    value={form.username}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(e) => {
                      set("username", e.target.value);
                    }}
                    data-testid="ssh-username"
                  />
                </div>
                <Field>
                  <span className="form-label" id="ssh-auth-label">
                    {t("adminRunnerSsh:auth")}
                  </span>
                  <div
                    className="seg seg-fill"
                    role="radiogroup"
                    aria-labelledby="ssh-auth-label"
                  >
                    {(["password", "key"] as const).map((kind) => (
                      <button
                        key={kind}
                        type="button"
                        role="radio"
                        aria-checked={form.authKind === kind}
                        className={
                          form.authKind === kind ? "active" : undefined
                        }
                        onClick={() => {
                          set("authKind", kind);
                        }}
                        data-testid={`ssh-auth-${kind}`}
                      >
                        {t(`adminRunnerSsh:authKind.${kind}`)}
                      </button>
                    ))}
                  </div>
                </Field>
                {form.authKind === "password" ? (
                  <Input
                    label={t("adminRunnerSsh:password")}
                    type="password"
                    value={form.password}
                    autoComplete="new-password"
                    onChange={(e) => {
                      set("password", e.target.value);
                    }}
                    data-testid="ssh-password"
                  />
                ) : (
                  <>
                    <Textarea
                      label={t("adminRunnerSsh:privateKey")}
                      hint={t("adminRunnerSsh:privateKeyHint")}
                      isMono
                      rows={5}
                      value={form.privateKey}
                      autoComplete="off"
                      spellCheck={false}
                      onChange={(e) => {
                        set("privateKey", e.target.value);
                      }}
                      data-testid="ssh-private-key"
                    />
                    <Input
                      label={t("adminRunnerSsh:passphrase")}
                      hint={t("adminRunnerSsh:passphraseHint")}
                      type="password"
                      value={form.passphrase}
                      autoComplete="new-password"
                      onChange={(e) => {
                        set("passphrase", e.target.value);
                      }}
                      data-testid="ssh-passphrase"
                    />
                  </>
                )}
                <div className="flex items-center" style={{ gap: "0.625rem" }}>
                  <Switch
                    checked={form.sudo}
                    onChange={(v) => {
                      set("sudo", v);
                    }}
                    label={t("adminRunnerSsh:sudo")}
                    describedBy="ssh-sudo-hint"
                    testId="ssh-sudo"
                  />
                  <div className="flex flex-col">
                    <span style={{ fontSize: "0.8125rem" }}>
                      {t("adminRunnerSsh:sudo")}
                    </span>
                    <span className="form-hint" id="ssh-sudo-hint">
                      {t("adminRunnerSsh:sudoHint")}
                    </span>
                  </div>
                </div>
                {!modelServer && (
                  <Input
                    label={t("name")}
                    hint={t("nameHint")}
                    value={form.name}
                    maxLength={40}
                    autoComplete="off"
                    onChange={(e) => {
                      set("name", e.target.value);
                    }}
                    data-testid="ssh-runner-name"
                  />
                )}
                <div
                  className="flex flex-col"
                  style={{
                    gap: "0.5rem",
                    padding: "0.625rem",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--r-2)",
                  }}
                >
                  <div
                    className="flex items-center"
                    style={{ gap: "0.625rem" }}
                  >
                    <Switch
                      checked={form.save}
                      disabled={!capability.data.can_save_credentials}
                      onChange={(v) => {
                        set("save", v);
                      }}
                      label={t("adminRunnerSsh:save")}
                      describedBy="ssh-save-hint"
                      testId="ssh-save"
                    />
                    <span style={{ fontSize: "0.8125rem" }}>
                      {t("adminRunnerSsh:save")}
                    </span>
                  </div>
                  <span className="form-hint" id="ssh-save-hint">
                    {capability.data.can_save_credentials
                      ? form.save
                        ? t("adminRunnerSsh:saveOn")
                        : t("adminRunnerSsh:saveOff")
                      : t("adminRunnerSsh:saveUnavailable")}
                  </span>
                  {form.save && (
                    <Input
                      label={t("adminRunnerSsh:label")}
                      value={form.label}
                      maxLength={80}
                      autoComplete="off"
                      onChange={(e) => {
                        set("label", e.target.value);
                      }}
                      data-testid="ssh-label"
                    />
                  )}
                </div>
                <div
                  className="flex items-center"
                  style={{ gap: "0.5rem", justifyContent: "flex-end" }}
                >
                  <Button type="button" variant="ghost" onClick={close}>
                    {t("adminOps:cancel")}
                  </Button>
                  <Button
                    type="submit"
                    disabled={!valid || probe.isPending}
                    data-testid="ssh-probe-submit"
                  >
                    {probe.isPending && <Spinner size="sm" />}
                    {t("adminRunnerSsh:connect")}
                  </Button>
                </div>
              </form>
            </>
          )}

          {stage === "fingerprint" && hostKey && (
            <div className="flex flex-col" style={{ gap: "0.75rem" }}>
              <p style={{ margin: 0, fontSize: "0.8125rem" }}>
                {t("adminRunnerSsh:fingerprintLead", {
                  host: form.host.trim(),
                  port: form.port,
                })}
              </p>
              <dl
                className="flex flex-col"
                style={{ gap: "0.25rem", margin: 0, fontSize: "0.8125rem" }}
              >
                <dt className="form-hint">{t("adminRunnerSsh:keyType")}</dt>
                <dd style={{ margin: 0 }} data-testid="ssh-key-type">
                  {hostKey.key_type}
                </dd>
                <dt className="form-hint">{t("adminRunnerSsh:fingerprint")}</dt>
                <dd
                  className="mono"
                  style={{ margin: 0, wordBreak: "break-all" }}
                  data-testid="ssh-fingerprint"
                >
                  {hostKey.fingerprint}
                </dd>
              </dl>
              <p className="form-hint" style={{ margin: 0 }}>
                {t("adminRunnerSsh:fingerprintHint")}
              </p>
              <div
                className="flex items-center"
                style={{ gap: "0.5rem", justifyContent: "flex-end" }}
              >
                <Button type="button" variant="ghost" onClick={close}>
                  {t("adminRunnerSsh:reject")}
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  disabled={confirm.isPending}
                  onClick={doConfirm}
                  data-testid="ssh-confirm"
                >
                  {confirm.isPending && <Spinner size="sm" />}
                  {t("adminRunnerSsh:trust")}
                </Button>
              </div>
            </div>
          )}

          {stage === "plan" && plan && (
            <div className="flex flex-col" style={{ gap: "0.75rem" }}>
              <p
                style={{ margin: 0, fontSize: "0.8125rem" }}
                data-testid="ssh-system"
              >
                {t("adminRunnerSsh:system", {
                  os: plan.system.distro || plan.system.os,
                  arch: plan.system.arch,
                  docker: plan.system.has_docker
                    ? t("adminRunnerSsh:dockerYes")
                    : t("adminRunnerSsh:dockerNo"),
                })}
              </p>
              {modelServer && (
                <div data-testid="ssh-model-summary">
                  <p style={{ margin: 0, fontSize: "0.8125rem" }}>
                    {t("adminModelServers:ssh.summary", {
                      engine: t(
                        `adminModelServers:engine.${modelServer.engine}`,
                      ),
                      model: modelServer.model,
                    })}
                  </p>
                  <Notice
                    tone={modelServer.exposure === "public" ? "warn" : "info"}
                    text={t(
                      `adminModelServers:ssh.exposure.${modelServer.exposure}`,
                    )}
                  />
                </div>
              )}
              <ol
                hidden={modelServer !== null}
                className="flex flex-col"
                style={{ gap: "0.25rem", margin: 0, paddingLeft: "1.25rem" }}
                data-testid="ssh-plan"
              >
                {plan.plan.map((step) => (
                  <li
                    key={step.key}
                    style={{ fontSize: "0.8125rem" }}
                    data-testid={`ssh-plan-${step.key}`}
                    data-action={step.action}
                  >
                    {t(`step.${step.key}`)}{" "}
                    <span className="form-hint">
                      {t(`adminRunnerSsh:action.${step.action}`)}
                    </span>
                  </li>
                ))}
              </ol>
              {needsDocker && (
                <div className="flex items-center" style={{ gap: "0.625rem" }}>
                  <Switch
                    checked={installDocker}
                    onChange={setInstallDocker}
                    label={t("adminRunnerSsh:installDocker")}
                    testId="ssh-install-docker"
                  />
                  <div className="flex flex-col">
                    <span style={{ fontSize: "0.8125rem" }}>
                      {t("adminRunnerSsh:installDocker")}
                    </span>
                    <span className="form-hint">
                      {t("adminRunnerSsh:installDockerHint")}
                    </span>
                  </div>
                </div>
              )}
              {blocked && (
                <div data-testid="ssh-blocked">
                  <Notice
                    tone="err"
                    role="alert"
                    text={t(`adminRunnerSsh:blockedStep.${blocked.key}`, {
                      defaultValue: t("adminRunnerSsh:blockedStep.default"),
                    })}
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
                  disabled={
                    !dockerOk || blocked !== undefined || install.isPending
                  }
                  onClick={startInstall}
                  data-testid="ssh-install"
                >
                  {install.isPending && <Spinner size="sm" />}
                  {t("local.start")}
                </Button>
              </div>
            </div>
          )}

          {stage === "progress" && (
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
                        text={errorText(t, current.error_code ?? "unexpected")}
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
                {current?.state === "failed" && session && (
                  <Button
                    type="button"
                    variant="primary"
                    onClick={() => {
                      setJobId(null);
                      startInstall();
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

// Словари мастера. Тексты формы, отпечатка и плана лежат в своём чанке runnerSsh
// и грузятся только при первом открытии окна. ops и runnerInstall (шаги, ход
// установки, общие отказы) нужны тоже: страница серверов моделей сама их не
// подключает, поэтому окно подтягивает весь набор.
const SSH_NAMESPACES: readonly AdminNamespace[] = [
  "ops",
  "runnerInstall",
  "runnerSsh",
];

type LocalesState = "loading" | "ready" | "failed";

const useSshLocales = (isOpen: boolean) => {
  const [state, setState] = useState<LocalesState>("loading");
  const [attempt, setAttempt] = useState(0);
  const wanted = isOpen && state !== "ready";
  useEffect(() => {
    if (!wanted) return;
    let live = true;
    loadAdminNamespaces(SSH_NAMESPACES).then(
      () => {
        if (live) setState("ready");
      },
      (error: unknown) => {
        reportIfChunkError(error);
        if (live) setState("failed");
      },
    );
    return () => {
      live = false;
    };
  }, [wanted, attempt]);
  const retry = () => {
    setState("loading");
    setAttempt((n) => n + 1);
  };
  return { state, retry };
};

/** Пока словари мастера не пришли: крутилка, а при провале сообщение и повтор. */
const LocalesGate = ({
  isOpen,
  onClose,
  failed,
  onRetry,
}: {
  isOpen: boolean;
  onClose: () => void;
  failed: boolean;
  onRetry: () => void;
}) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        failed
          ? t("uiPrimitives:chunkError.title")
          : t("uiPrimitives:spinner.loading")
      }
      width={640}
    >
      {failed ? (
        <div
          className="flex flex-col items-start"
          style={{ gap: "0.75rem" }}
          data-testid="ssh-locales-error"
        >
          <Notice
            tone="err"
            role="alert"
            text={t("uiPrimitives:chunkError.text")}
          />
          <Button
            size="sm"
            variant="ghost"
            type="button"
            data-testid="ssh-locales-retry"
            onClick={onRetry}
          >
            {t("uiPrimitives:dataTable.retry")}
          </Button>
        </div>
      ) : (
        <div
          className="flex justify-center"
          style={{ padding: "2rem" }}
          data-testid="ssh-locales-loading"
        >
          <Spinner />
        </div>
      )}
    </Modal>
  );
};

/**
 * Установка раннера по SSH: данные хоста, подтверждение отпечатка ключа, план по найденному на хосте, ход установки.
 * Окно само подключает свои словари, поэтому его можно открыть с любой страницы админки.
 */
export const SshInstallDialog = (props: SshInstallDialogProps) => {
  const locales = useSshLocales(props.isOpen);
  if (locales.state === "ready") return <SshInstallDialogBody {...props} />;
  return (
    <LocalesGate
      isOpen={props.isOpen}
      onClose={props.onClose}
      failed={locales.state === "failed"}
      onRetry={locales.retry}
    />
  );
};
