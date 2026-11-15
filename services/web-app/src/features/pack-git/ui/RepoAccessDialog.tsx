import { useState } from "react";
import { KeyRound, Lock, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useCredentials } from "@entities/git-remote";
import type { PackWorkspace } from "@entities/pack-studio";
import {
  CredentialCheckCard,
  RepoTokenHelp,
  ReplaceTokenDialog,
} from "@features/git-remote";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type RepoAccessDialogProps = {
  workspace: PackWorkspace;
  isOpen: boolean;
  onClose: () => void;
};

/**
 * Доступ пространства к репозиторию (template-studio.md, 4.2): служебный доступ
 * установки или личный токен из «Доступов git». Токен проверяется и выпускается
 * под профиль прав «packs» (ветка, PR, статус проверок); замена токена сохраняет
 * доступ, и пространство сразу ходит с новым.
 */
export const RepoAccessDialog = ({
  workspace,
  isOpen,
  onClose,
}: RepoAccessDialogProps) => {
  const { t } = useTranslation("packStudio");
  const credentials = useCredentials(
    isOpen && workspace.credential_id !== null,
  );
  const [replacing, setReplacing] = useState(false);
  const credential =
    credentials.data?.find((c) => c.id === workspace.credential_id) ?? null;

  let body: React.ReactNode;
  if (workspace.service_access) {
    body = (
      <div className="ps-access-row" data-testid="git-access-service">
        <ShieldCheck size="1rem" aria-hidden="true" className="ps-ci-ok" />
        <div className="ps-access-text">
          <strong>{t("git.access.serviceTitle")}</strong>
          <span>{t("git.access.serviceLead")}</span>
        </div>
      </div>
    );
  } else if (workspace.credential_id === null) {
    body = (
      <>
        <Notice tone="info" role="status" text={t("git.access.noneLead")} />
        {workspace.url && (
          <RepoTokenHelp url={workspace.url} profile="packs" defaultOpen />
        )}
      </>
    );
  } else if (credentials.isPending) {
    body = (
      <div className="flex justify-center" style={{ padding: "1.5rem" }}>
        <Spinner size="md" />
      </div>
    );
  } else if (!credential) {
    body = <Notice tone="warn" role="alert" text={t("git.access.missing")} />;
  } else {
    body = (
      <>
        <div className="ps-access-row" data-testid="git-access-credential">
          {credential.kind === "ssh_key" ? (
            <KeyRound size="1rem" aria-hidden="true" />
          ) : (
            <Lock size="1rem" aria-hidden="true" />
          )}
          <div className="ps-access-text">
            <strong className="truncate">{credential.label}</strong>
            <span className="mono">
              {credential.host}
              {credential.token_family ? ` · ${credential.token_family}…` : ""}
            </span>
          </div>
          {credential.kind === "pat" && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                setReplacing(true);
              }}
              data-testid="git-access-replace"
            >
              {t("git.access.replace")}
            </Button>
          )}
        </div>
        <p className="ps-dialog-text">{t("git.access.checkLead")}</p>
        <CredentialCheckCard
          credential={credential}
          profile="packs"
          checkLabel={t("git.access.check")}
        />
        {workspace.url && (
          <details className="sync-details">
            <summary>{t("git.access.newToken")}</summary>
            <div style={{ marginTop: "0.5rem" }}>
              <RepoTokenHelp url={workspace.url} profile="packs" defaultOpen />
            </div>
          </details>
        )}
        {replacing && (
          <ReplaceTokenDialog
            credential={credential}
            profile="packs"
            onClose={() => {
              setReplacing(false);
            }}
          />
        )}
      </>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("git.access.title")}
      description={workspace.url ?? undefined}
      width={600}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t("git.access.close")}
        </Button>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="git-access"
      >
        {body}
      </div>
    </Modal>
  );
};
