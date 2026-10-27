import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCredentials,
  useGitHosts,
  useProbe,
  useSecretsStatus,
  type Probe,
} from "@entities/git-remote";
import {
  describeGitError,
  useConnectRemote,
  useDisconnectRemote,
  useFetchRemote,
  useGitContents,
  useStartSync,
  useSyncStatus,
  useSyncUiStore,
  useUpdateGitSettings,
  type CloneTarget,
  type ConnectDialogMode,
  type SyncStatusView,
} from "@entities/git-sync";
import { useProfile } from "@entities/profile";
import { useProject } from "@entities/project";
import { flushPendingSaves, toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import { parseRemoteUrl } from "../lib/parseRemoteUrl";
import { useHostProvider } from "../model/useHostProvider";
import {
  outcomeFromError,
  outcomeFromProbe,
  type CheckOutcome,
} from "../model/probeOutcome";
import { AccessStep } from "./AccessStep";
import { CheckStep } from "./CheckStep";
import { HostKeyDialog, type HostKeyMode } from "./HostKeyDialog";
import { ProfileStep } from "./ProfileStep";
import { RepositoryStep } from "./RepositoryStep";
import { TlsTrustDialog } from "./TlsTrustDialog";

export type ConnectStep = "profile" | "repo" | "access" | "check";

export type { CloneTarget };

export type ConnectFlowProps = {
  projectId: string;
  mode: ConnectDialogMode;
  onClose: () => void;
  onCloneInstead?: ((target: CloneTarget) => void) | undefined;
  /** Адрес, с которого начать (галерея и демо); обычно окно открывается с пустым полем. */
  initialUrl?: string | undefined;
};

const STEP_IDS = ["repo", "access", "check"] as const;

const isHostKeyCode = (
  code: string,
): code is "host_key_unknown" | "host_key_changed" =>
  code === "host_key_unknown" || code === "host_key_changed";

const isTlsCode = (
  code: string,
): code is "tls_untrusted_ca" | "tls_pin_mismatch" =>
  code === "tls_untrusted_ca" || code === "tls_pin_mismatch";

const Loading = () => {
  const { t } = useTranslation("gitRemote");
  return (
    <div
      className="flex items-center dim"
      role="status"
      style={{ gap: 8, minHeight: 160, justifyContent: "center" }}
    >
      <Spinner size="sm" />
      {t("connect.loading")}
    </div>
  );
};

// Содержимое окна подключения: три шага (адрес, доступ, проверка) и, если не
// хватает имени автора, перед ними короткое «Представься». Состояние живёт в
// теле и сбрасывается вместе с закрытием окна, потому что окно размонтирует его.
// Обновление доступа начинается с адреса подключённого репозитория, поэтому тело
// монтируется, когда состояние проекта уже известно.
export const ConnectFlow = (props: ConnectFlowProps) => {
  const statusQuery = useSyncStatus(props.projectId);
  if (props.mode === "fix_access" && statusQuery.isPending) return <Loading />;
  return <ConnectFlowBody {...props} status={statusQuery.data} />;
};

const ConnectFlowBody = ({
  projectId,
  mode,
  status,
  onClose,
  onCloneInstead,
  initialUrl,
}: ConnectFlowProps & { status: SyncStatusView | undefined }) => {
  const { t } = useTranslation("gitRemote");

  // Подключение, с которого начали. Окно не должно менять режим на ходу: если
  // замена доступа оборвётся на полпути и проект на миг останется без
  // репозитория, мы всё равно остаёмся в «обновить доступ».
  const [remote] = useState(status?.remote ?? null);
  const fixing = mode === "fix_access" && remote !== null;

  const profileQuery = useProfile();
  const projectQuery = useProject(projectId);
  const contentsQuery = useGitContents(projectId, !fixing);
  const credentialsQuery = useCredentials();
  const secretsQuery = useSecretsStatus();
  const hostsQuery = useGitHosts();

  const probe = useProbe();
  const connectRemote = useConnectRemote();
  const disconnectRemote = useDisconnectRemote();
  const fetchRemote = useFetchRemote();
  const startSync = useStartSync();
  const updateSettings = useUpdateGitSettings();

  const [step, setStep] = useState<ConnectStep | null>(null);
  const [urlText, setUrlText] = useState(
    remote?.display_url ?? initialUrl ?? "",
  );
  const [tokenStripped, setTokenStripped] = useState(false);
  const [branch, setBranch] = useState(fixing ? remote.branch : "");
  const [ndaAck, setNdaAck] = useState(false);
  const [credentialId, setCredentialId] = useState<string | null>(null);
  const [adoptConfirmed, setAdoptConfirmed] = useState(false);
  const [outcome, setOutcome] = useState<CheckOutcome | null>(null);
  const [probeResult, setProbeResult] = useState<Probe | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [hostKeyOpen, setHostKeyOpen] = useState(false);
  const [tlsOpen, setTlsOpen] = useState(false);
  const runId = useRef(0);

  // Открытый http разрешён только тому подключению, которое уже живёт на нём
  // (сервер пустил его по своей политике): иначе обновить доступ было бы нечем.
  const insecureHttp = fixing && remote.insecure_http;
  const parsed = useMemo(
    () =>
      parseRemoteUrl(urlText, { allow_local: true, allow_http: insecureHttp }),
    [urlText, insecureHttp],
  );
  // Провайдер решён с учётом выбора человека и ответа сервера: подсказки и
  // ссылки на следующих шагах берут его, а не догадку по виду адреса.
  const hostProvider = useHostProvider(
    parsed.ok ? parsed.url : null,
    probeResult?.provider_info,
  );
  const repoUrl = hostProvider.url;

  // Токен из адреса убираем и из самого поля: «мы его убрали» должно быть правдой.
  const changeUrl = (value: string): void => {
    const next = parseRemoteUrl(value, { allow_local: true });
    // Вставка или автозаполнение приходят одним куском, а не по символу.
    const pasted = value.length - urlText.length > 1;
    if (pasted && next.ok && next.url.token_stripped) {
      setUrlText(next.url.display_url);
      setTokenStripped(true);
      return;
    }
    setUrlText(value);
    setTokenStripped(false);
  };
  const commitUrl = (): void => {
    if (parsed.ok && parsed.url.token_stripped) {
      setUrlText(parsed.url.display_url);
      setTokenStripped(true);
    }
  };

  // Шаг, с которого начинаем, когда профиль уже известен.
  const firstStep: ConnectStep = fixing ? "access" : "repo";
  const currentStep: ConnectStep | null =
    step ??
    (profileQuery.isLoading
      ? null
      : profileQuery.data?.is_default
        ? "profile"
        : firstStep);

  const ndaRequired =
    !fixing &&
    (projectQuery.data?.meta?.nda === true ||
      (contentsQuery.data?.nda_files ?? 0) > 0);

  // --- проверка адреса --------------------------------------------------------

  const runCheck = useCallback(
    async (
      overrides: { credentialId?: string | null; branch?: string } = {},
    ) => {
      if (!repoUrl) return;
      // null в overrides значит «без доступа», а не «возьми прежний».
      const id =
        overrides.credentialId !== undefined
          ? overrides.credentialId
          : credentialId;
      const branchValue = (overrides.branch ?? branch).trim();
      runId.current += 1;
      const run = runId.current;
      setStep("check");
      setOutcome(null);
      setProbeResult(null);
      setAdoptConfirmed(false);
      setHostKeyOpen(false);
      setTlsOpen(false);
      let result: CheckOutcome;
      let answer: Probe | null = null;
      try {
        answer = await probe.mutateAsync({
          url: repoUrl.display_url,
          credential_id: id,
          project_id: projectId,
          ...(branchValue !== "" ? { branch: branchValue } : {}),
          ...(insecureHttp ? { insecure_http: true } : {}),
        });
        result = outcomeFromProbe(answer);
      } catch (error) {
        result = outcomeFromError(error);
      }
      // Пока шла проверка, человек мог уйти назад или повторить её.
      if (run !== runId.current) return;
      setProbeResult(answer);
      setOutcome(result);
      if (result.kind === "error" && isHostKeyCode(result.issue.code)) {
        setHostKeyOpen(true);
      }
      if (result.kind === "error" && isTlsCode(result.issue.code)) {
        setTlsOpen(true);
      }
    },
    [branch, credentialId, insecureHttp, probe, projectId, repoUrl],
  );

  const goTo = (next: ConnectStep): void => {
    // Ответ на прежнюю проверку больше не нужен.
    runId.current += 1;
    setStep(next);
  };

  const continueWithCredential = (id: string | null): void => {
    setCredentialId(id);
    void runCheck({ credentialId: id });
  };

  // --- подключение ------------------------------------------------------------

  const connect = async (options: {
    sync: boolean;
    adopt: boolean;
  }): Promise<void> => {
    if (!repoUrl) return;
    setIsConnecting(true);
    try {
      if (fixing) {
        const boundId = remote.credential?.id ?? null;
        if (credentialId !== boundId) {
          // Проект связан с другим доступом (или ни с каким): отвязываем и
          // подключаем тот же адрес заново. Версии на компьютере остаются.
          await disconnectRemote.mutateAsync({ projectId });
          try {
            await connectRemote.mutateAsync({
              projectId,
              params: {
                url: repoUrl.display_url,
                credential_id: credentialId,
                ...(branch.trim() !== ""
                  ? { remote_branch: branch.trim() }
                  : {}),
                ...(insecureHttp ? { insecure_http: true } : {}),
              },
            });
          } catch (error) {
            // Не оставляем проект без репозитория: возвращаем прежний доступ.
            await connectRemote
              .mutateAsync({
                projectId,
                params: {
                  url: remote.display_url,
                  credential_id: boundId,
                  remote_branch: remote.branch,
                  ...(insecureHttp ? { insecure_http: true } : {}),
                },
              })
              .catch(() => undefined);
            throw error;
          }
        } else {
          await fetchRemote.mutateAsync(projectId);
        }
        toast.success(t("done.accessUpdated"));
        onClose();
        return;
      }

      await connectRemote.mutateAsync({
        projectId,
        params: {
          url: repoUrl.display_url,
          credential_id: credentialId,
          ...(branch.trim() !== "" ? { remote_branch: branch.trim() } : {}),
          ...(options.adopt ? { adopt: "merge_remote" } : {}),
        },
      });
      const repo = [repoUrl.owner, repoUrl.repo].filter(Boolean).join("/");
      if (options.sync) {
        await startSyncAfterConnect(repo);
      } else {
        toast.success(t("done.connected", { repo }), {
          title: t("done.title"),
        });
      }
      onClose();
    } catch (error) {
      const result = outcomeFromError(error);
      if (result.kind === "error" && result.issue.code === "profile_required") {
        setStep("profile");
        return;
      }
      setOutcome(result);
      if (result.kind === "error" && isHostKeyCode(result.issue.code)) {
        setHostKeyOpen(true);
      }
      if (result.kind === "error" && isTlsCode(result.issue.code)) {
        setTlsOpen(true);
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // Репозиторий уже подключён; если запуск не удался, об этом скажет тост, а не окно.
  const startSyncAfterConnect = async (repo: string): Promise<void> => {
    toast.success(t("done.connectedSyncing", { repo }), {
      title: t("done.title"),
    });
    try {
      await flushPendingSaves();
      await startSync.mutateAsync(projectId);
      useSyncUiStore.getState().setPopoverOpen(true);
    } catch (error) {
      toast.error(describeGitError(error, t("done.syncFailed")), {
        title: t("done.syncFailedTitle"),
      });
    }
  };

  // --- что показывать ---------------------------------------------------------

  const stepperSteps: StepperStep[] = STEP_IDS.map((id) => ({
    id,
    label: t(`connect.steps.${id}`),
  }));

  const sharedFolder =
    status?.shared_folder && !status.shared_folder.acknowledged
      ? { provider: status.shared_folder.provider }
      : null;

  const issue = outcome?.kind === "error" ? outcome.issue : null;
  const hostKeyMode: HostKeyMode =
    issue?.code === "host_key_changed" ? "changed" : "unknown";
  const knownFingerprints =
    hostsQuery.data?.find(
      (known) =>
        known.host === repoUrl?.host && (known.port ?? null) === repoUrl.port,
    )?.fingerprints_sha256 ?? [];

  if (currentStep === null) return <Loading />;

  const leadKey =
    currentStep === "access" && fixing
      ? "connect.lead.accessFix"
      : currentStep === "check" && outcome !== null
        ? "connect.lead.checked"
        : `connect.lead.${currentStep}`;

  return (
    <div className="flex flex-col" style={{ gap: 14 }}>
      {currentStep !== "profile" && (
        <Stepper
          steps={stepperSteps}
          current={currentStep}
          busy={currentStep === "check" && outcome === null}
          label={t("connect.steps.label")}
        />
      )}
      <p className="dim" style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}>
        {t(leadKey)}
      </p>

      {currentStep === "profile" && (
        <ProfileStep
          onCancel={onClose}
          onSaved={() => {
            goTo(firstStep);
          }}
        />
      )}

      {currentStep === "repo" && (
        <RepositoryStep
          url={urlText}
          onUrlChange={changeUrl}
          onUrlCommit={commitUrl}
          tokenStripped={tokenStripped}
          branch={branch}
          onBranchChange={setBranch}
          parsed={parsed}
          ndaRequired={ndaRequired}
          ndaAck={ndaAck}
          onNdaAckChange={setNdaAck}
          contents={{
            data: contentsQuery.data,
            isLoading: contentsQuery.isLoading,
            isError: contentsQuery.isError,
            refetch: () => {
              void contentsQuery.refetch();
            },
          }}
          sharedFolder={sharedFolder}
          onAcknowledgeShared={() => {
            updateSettings.mutate({
              projectId,
              params: { shared_folder_ack: true },
            });
          }}
          isAcknowledging={updateSettings.isPending}
          onCancel={onClose}
          onNext={() => {
            // Папка на компьютере не требует доступа: сразу к проверке.
            if (repoUrl?.kind === "file") continueWithCredential(null);
            else goTo("access");
          }}
        />
      )}

      {currentStep === "access" && repoUrl && (
        <AccessStep
          url={repoUrl}
          fixing={fixing}
          bound={remote?.credential ?? null}
          credentials={credentialsQuery.data ?? []}
          isLoadingCredentials={credentialsQuery.isLoading}
          secretsOk={secretsQuery.data?.ok ?? true}
          projectName={projectQuery.data?.name ?? null}
          onContinue={(id) => {
            continueWithCredential(id);
          }}
          onBack={() => {
            if (fixing) onClose();
            else goTo("repo");
          }}
          onSwitchUrl={setUrlText}
        />
      )}

      {currentStep === "check" && (
        <CheckStep
          outcome={outcome}
          probe={probeResult}
          contents={contentsQuery.data}
          fixing={fixing}
          isConnecting={isConnecting}
          adoptConfirmed={adoptConfirmed}
          publicAccess={credentialId === null && repoUrl?.kind !== "file"}
          onAdoptConfirmedChange={setAdoptConfirmed}
          onBack={() => {
            goTo(fixing || repoUrl?.kind !== "file" ? "access" : "repo");
          }}
          onCancel={onClose}
          onConnect={(sync) => {
            void connect({ sync, adopt: false });
          }}
          onAdopt={() => {
            void connect({ sync: true, adopt: true });
          }}
          onRetry={() => {
            void runCheck();
          }}
          onBackToRepo={() => {
            goTo("repo");
          }}
          onBackToAccess={() => {
            goTo(repoUrl?.kind === "file" ? "repo" : "access");
          }}
          onReviewHostKey={() => {
            setHostKeyOpen(true);
          }}
          onReviewCertificate={() => {
            setTlsOpen(true);
          }}
          onPickBranch={(picked) => {
            setBranch(picked);
            void runCheck({ branch: picked });
          }}
          onCloneInstead={
            onCloneInstead && repoUrl
              ? () => {
                  onCloneInstead({
                    url: repoUrl.display_url,
                    credentialId,
                  });
                  onClose();
                }
              : undefined
          }
        />
      )}

      {repoUrl?.host && (
        <TlsTrustDialog
          isOpen={tlsOpen && issue !== null && isTlsCode(issue.code)}
          mode={
            issue?.code === "tls_pin_mismatch" ? "pin_mismatch" : "untrusted"
          }
          host={repoUrl.host}
          port={hostProvider.port}
          certificate={issue?.certificate ?? null}
          expected={issue?.expectedFingerprint ?? null}
          actual={issue?.actualFingerprint ?? null}
          onTrusted={() => {
            setTlsOpen(false);
            void runCheck();
          }}
          onClose={() => {
            setTlsOpen(false);
          }}
        />
      )}

      {repoUrl?.host && (
        <HostKeyDialog
          isOpen={hostKeyOpen && issue !== null && isHostKeyCode(issue.code)}
          mode={hostKeyMode}
          host={repoUrl.host}
          port={repoUrl.port}
          keys={issue?.hostKeys ?? []}
          knownFingerprints={knownFingerprints}
          onTrusted={() => {
            setHostKeyOpen(false);
            void runCheck();
          }}
          onClose={() => {
            setHostKeyOpen(false);
          }}
        />
      )}
    </div>
  );
};
