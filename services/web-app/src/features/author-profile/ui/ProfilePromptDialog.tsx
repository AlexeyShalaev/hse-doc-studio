import { useTranslation } from "react-i18next";
import { ProfileForm, useProfile, type Profile } from "@entities/profile";
import { describeGitError } from "@entities/git-sync";
import { Modal } from "@shared/ui/Modal";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type ProfilePromptReason = "connect" | "sync" | "clone";

export type ProfilePromptDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  /** Профиль сохранён (или уже был задан): можно продолжать прерванное действие. */
  onSaved?: (profile: Profile) => void;
  /** Что именно прервалось: от этого зависит пояснение под заголовком. */
  reason?: ProfilePromptReason;
};

// Окно «Представься» на случай profile_required: подключение, синхронизация и
// клонирование не начинаются, пока не указаны имя и e-mail автора.
export const ProfilePromptDialog = ({
  isOpen,
  onClose,
  onSaved,
  reason,
}: ProfilePromptDialogProps) => {
  const { t } = useTranslation("profile");
  const profileQuery = useProfile();
  const profile = profileQuery.data;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      width={460}
      title={t("dialog.title")}
      description={
        reason ? t(`dialog.reason.${reason}`) : t("dialog.description")
      }
    >
      {profileQuery.isLoading && (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="dim">{t("section.loading")}</span>
        </div>
      )}
      {profileQuery.isError && !profile && (
        <Notice
          tone="err"
          role="alert"
          text={describeGitError(profileQuery.error, t("section.loadFailed"))}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void profileQuery.refetch();
              }}
            >
              {t("section.retry")}
            </button>
          }
        />
      )}
      {profile && (
        <ProfileForm
          profile={profile}
          variant="dialog"
          autoFocus
          allowUnchanged
          submitLabel={t("dialog.continue")}
          cancelLabel={t("dialog.later")}
          onCancel={onClose}
          onSaved={onSaved}
        />
      )}
    </Modal>
  );
};
