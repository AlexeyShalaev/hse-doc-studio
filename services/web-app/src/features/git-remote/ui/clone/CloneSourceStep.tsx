import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCredentials,
  useGitHosts,
  useSecretsStatus,
} from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { isEncryptedBundleName } from "../../lib/cloneNames";
import { useHostProvider } from "../../model/useHostProvider";
import { useRemoteAuth } from "../../model/useRemoteAuth";
import type { CloneSource, CloneTab } from "../../model/useCloneSource";
import { HostKeyDialog, type HostKeyMode } from "../HostKeyDialog";
import { RemoteAuthFields } from "../RemoteAuthFields";
import { RepoUrlField } from "../RepoUrlField";
import { TlsTrustDialog } from "../TlsTrustDialog";
import { CloneBundleSource } from "./CloneBundleSource";
import { CloneStepLayout } from "./CloneStepLayout";
import { CloneVerdictCard } from "./CloneVerdictCard";

export type CloneSourceStepProps = {
  source: CloneSource;
  /** Отказ запуска, с которым вернули на этот шаг (bundle: файл, пароль). */
  bundleError: { code: string; message: string } | null;
  onCancel: () => void;
  onNext: () => void;
};

const TABS: CloneTab[] = ["url", "bundle"];

const isHostKeyCode = (
  code: string,
): code is "host_key_unknown" | "host_key_changed" =>
  code === "host_key_unknown" || code === "host_key_changed";

const isTlsCode = (
  code: string,
): code is "tls_untrusted_ca" | "tls_pin_mismatch" =>
  code === "tls_untrusted_ca" || code === "tls_pin_mismatch";

// Шаг 1. Откуда клонировать: адрес репозитория с проверкой доступа или файл
// bundle. Результат проверки показывает, что за проект там лежит и как он откроется.
export const CloneSourceStep = ({
  source,
  bundleError,
  onCancel,
  onNext,
}: CloneSourceStepProps) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const credentialsQuery = useCredentials();
  const secretsQuery = useSecretsStatus();
  const hostsQuery = useGitHosts();
  // Результат проверки, для которого окно ключа сервера уже закрыли.
  const [hostKeyClosedFor, setHostKeyClosedFor] = useState<unknown>(null);
  const [tlsClosedFor, setTlsClosedFor] = useState<unknown>(null);
  const [submitted, setSubmitted] = useState(false);

  const { tab, parsed, check } = source;
  // Провайдер решён с учётом выбора человека и ответа сервера.
  const hostProvider = useHostProvider(
    source.repoUrl,
    check.status === "done" ? check.probe?.provider_info : null,
  );
  const repoUrl = hostProvider.url;
  const secretsOk = secretsQuery.data?.ok ?? true;
  const verdict = check.status === "done" ? check.verdict : null;
  const ready = verdict?.kind === "ready";
  const issue = verdict?.kind === "error" ? verdict.issue : null;
  const needsAuth = repoUrl !== null && repoUrl.kind !== "file";
  const showAuth = tab === "url" && needsAuth && check.status === "idle";

  const auth = useRemoteAuth({
    url: repoUrl,
    fixing: false,
    bound: null,
    credentials: credentialsQuery.data ?? [],
    secretsOk,
    allowAnonymous: true,
    initialCredentialId: source.credentialId,
    onResolved: (id) => {
      void source.runCheck({ credentialId: id });
    },
  });

  const bundleReady =
    source.bundleFile !== null &&
    (!isEncryptedBundleName(source.bundleFile.name) ||
      source.bundlePassword.trim() !== "");
  const checking = check.status === "checking";

  // Что делает главная кнопка: проверяет адрес, идёт дальше или ждёт.
  const submit = (): void => {
    setSubmitted(true);
    source.commitUrl();
    if (tab === "bundle") {
      if (bundleReady) onNext();
      return;
    }
    if (ready) {
      onNext();
      return;
    }
    if (!repoUrl || checking || check.status === "done") return;
    if (!needsAuth) {
      void source.runCheck({ credentialId: null });
      return;
    }
    if (auth.canSubmit) auth.submit();
  };

  // Пока адрес не проверен, кнопка проверяет; после проверки она ведёт дальше
  // (и отключена, если проверка не пустила: причина и действия в карточке ниже).
  const canSubmit =
    tab === "bundle"
      ? bundleReady
      : check.status === "done"
        ? ready
        : repoUrl !== null && !checking && (!needsAuth || auth.canSubmit);

  const actionLabel =
    tab === "bundle" || check.status === "done"
      ? t("clone.next")
      : needsAuth && auth.method === "pat" && auth.creatingPat
        ? t("gitAccess:step.saveAndCheck")
        : t("clone.source.check");

  const hostKeyMode: HostKeyMode =
    issue?.code === "host_key_changed" ? "changed" : "unknown";
  const knownFingerprints =
    hostsQuery.data?.find(
      (known) =>
        known.host === repoUrl?.host && (known.port ?? null) === repoUrl.port,
    )?.fingerprints_sha256 ?? [];

  const openHostKey = (): void => {
    setHostKeyClosedFor(null);
  };

  // Незнакомый или изменившийся ключ сервера спрашиваем сразу, как в окне подключения.
  const hostKeyOpen =
    issue !== null && isHostKeyCode(issue.code) && hostKeyClosedFor !== check;
  // Сертификат внутреннего сервера спрашиваем так же сразу.
  const tlsOpen =
    issue !== null && isTlsCode(issue.code) && tlsClosedFor !== check;

  return (
    <CloneStepLayout
      id="clone-source"
      aria-label={t("clone.steps.source")}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      start={
        <button type="button" className="btn" onClick={onCancel}>
          {t("clone.cancel")}
        </button>
      }
      end={
        <button type="submit" className="btn primary" disabled={!canSubmit}>
          {(checking || auth.isSaving) && <Spinner size="sm" />}
          {actionLabel}
        </button>
      }
    >
      <div
        className="seg"
        role="tablist"
        aria-label={t("clone.source.tabs.label")}
        style={{ alignSelf: "flex-start" }}
      >
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            id={`${uid}-tab-${value}`}
            aria-selected={tab === value}
            aria-controls={`${uid}-panel-${value}`}
            className={tab === value ? "active" : undefined}
            onClick={() => {
              source.setTab(value);
            }}
          >
            {t(`clone.source.tabs.${value}`)}
          </button>
        ))}
      </div>

      {tab === "url" ? (
        <div
          role="tabpanel"
          id={`${uid}-panel-url`}
          aria-labelledby={`${uid}-tab-url`}
          className="flex flex-col"
          style={{ gap: 16 }}
        >
          <RepoUrlField
            url={source.urlText}
            onChange={source.changeUrl}
            onCommit={source.commitUrl}
            parsed={parsed}
            tokenStripped={source.tokenStripped}
            forceError={submitted}
            disabled={checking}
          />

          {source.error && (
            <Notice tone="err" role="alert" text={source.error} />
          )}

          {showAuth && (
            <section
              className="flex flex-col"
              style={{ gap: 12 }}
              aria-label={t("clone.source.access")}
              data-testid="clone-access"
            >
              <RemoteAuthFields
                auth={auth}
                url={repoUrl}
                isLoadingCredentials={credentialsQuery.isLoading}
                secretsOk={secretsOk}
                onSwitchUrl={source.setUrlText}
              />
            </section>
          )}

          {checking && (
            <div
              role="status"
              className="flex items-start"
              data-testid="clone-checking"
              style={{
                gap: 10,
                padding: "12px 14px",
                borderRadius: "var(--r-3)",
                border: "1px solid var(--border)",
                background: "var(--bg-1)",
              }}
            >
              <Spinner size="sm" />
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>
                  {t("clone.source.checking.title")}
                </div>
                <div className="dim" style={{ fontSize: 12.5, marginTop: 2 }}>
                  {t("clone.source.checking.text")}
                </div>
              </div>
            </div>
          )}

          {verdict && (
            <CloneVerdictCard
              verdict={verdict}
              probe={check.status === "done" ? check.probe : null}
              url={repoUrl}
              branch={source.branch}
              onPickBranch={(picked) => {
                source.setBranch(picked);
                void source.runCheck({ branch: picked });
              }}
              onChange={source.resetCheck}
              issueHandlers={{
                onRetry: () => {
                  void source.runCheck();
                },
                onBackToRepo: source.resetCheck,
                onBackToAccess: source.resetCheck,
                onReviewHostKey: openHostKey,
                onReviewCertificate: () => {
                  setTlsClosedFor(null);
                },
                onPickBranch: (picked) => {
                  source.setBranch(picked);
                  void source.runCheck({ branch: picked });
                },
                onClose: onCancel,
              }}
            />
          )}
        </div>
      ) : (
        <div
          role="tabpanel"
          id={`${uid}-panel-bundle`}
          aria-labelledby={`${uid}-tab-bundle`}
        >
          <CloneBundleSource
            file={source.bundleFile}
            onFileChange={source.setBundleFile}
            password={source.bundlePassword}
            onPasswordChange={source.setBundlePassword}
            error={bundleError}
          />
        </div>
      )}

      {tab === "url" && repoUrl?.host && (
        <TlsTrustDialog
          isOpen={tlsOpen}
          mode={
            issue?.code === "tls_pin_mismatch" ? "pin_mismatch" : "untrusted"
          }
          host={repoUrl.host}
          port={hostProvider.port}
          certificate={issue?.certificate ?? null}
          onTrusted={() => {
            void source.runCheck();
          }}
          onClose={() => {
            setTlsClosedFor(check);
          }}
        />
      )}

      {tab === "url" && repoUrl?.host && (
        <HostKeyDialog
          isOpen={hostKeyOpen}
          mode={hostKeyMode}
          host={repoUrl.host}
          port={repoUrl.port}
          keys={issue?.hostKeys ?? []}
          knownFingerprints={knownFingerprints}
          onTrusted={() => {
            void source.runCheck();
          }}
          onClose={() => {
            setHostKeyClosedFor(check);
          }}
        />
      )}
    </CloneStepLayout>
  );
};
