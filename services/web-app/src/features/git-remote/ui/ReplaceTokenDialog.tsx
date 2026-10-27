import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  providerOfHost,
  useHostSettings,
  useUpdateCredential,
  type GitCredential,
} from "@entities/git-remote";
import { describeGitError } from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui/Modal";
import { Spinner } from "@shared/ui/Spinner";
import { urlForHost } from "../lib/hostUrl";
import { PatPanel, type PatDraft } from "./PatPanel";

export type ReplaceTokenDialogProps = {
  credential: GitCredential;
  onClose: () => void;
};

const EMPTY_DRAFT: PatDraft = { token: "", username: "", label: "" };

// Замена токена у сохранённого доступа. Новый токен живёт только в состоянии
// окна и стирается сразу после запроса, чем бы тот ни кончился.
export const ReplaceTokenDialog = ({
  credential,
  onClose,
}: ReplaceTokenDialogProps) => {
  const { t } = useTranslation("gitAccess");
  const update = useUpdateCredential();
  const [draft, setDraft] = useState<PatDraft>(EMPTY_DRAFT);
  const [showToken, setShowToken] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Памятка «как получить токен» зависит только от сервера. Адрес репозитория
  // доступу не принадлежит, поэтому подставляем условный: owner/repo.
  const hostSettings = useHostSettings();
  const provider = providerOfHost(credential.host, null, hostSettings.data).id;
  const url = useMemo(
    () => urlForHost(credential.host, provider),
    [credential.host, provider],
  );

  const close = (): void => {
    if (update.isPending) return;
    setDraft(EMPTY_DRAFT);
    setShowToken(false);
    setError(null);
    onClose();
  };

  const save = async (): Promise<void> => {
    const token = draft.token.trim();
    if (token === "") return;
    setError(null);
    try {
      await update.mutateAsync({ id: credential.id, params: { token } });
      toast.success(t("access.credentials.replaceDialog.done"));
      onClose();
    } catch (caught) {
      setError(
        describeGitError(caught, t("access.credentials.replaceDialog.failed")),
      );
    } finally {
      setDraft(EMPTY_DRAFT);
      setShowToken(false);
    }
  };

  return (
    <Modal
      isOpen
      onClose={close}
      width={500}
      title={t("access.credentials.replaceDialog.title")}
      description={t("access.credentials.replaceDialog.description", {
        host: credential.host,
      })}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={close}
            disabled={update.isPending}
          >
            {t("access.credentials.replaceDialog.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={draft.token.trim() === "" || update.isPending}
            onClick={() => {
              void save();
            }}
          >
            {update.isPending && <Spinner size="sm" />}
            {t("access.credentials.replaceDialog.save")}
          </button>
        </>
      }
    >
      <PatPanel
        draft={draft}
        onChange={setDraft}
        showToken={showToken}
        onToggleShowToken={() => {
          setShowToken((shown) => !shown);
        }}
        url={url}
        existing={credential}
        disabled={update.isPending}
        error={error}
        helpOpen={false}
      />
    </Modal>
  );
};
