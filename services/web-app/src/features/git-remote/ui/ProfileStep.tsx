import { useTranslation } from "react-i18next";
import { describeGitError } from "@entities/git-sync";
import { ProfileForm, useProfile } from "@entities/profile";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

export type ProfileStepProps = {
  onSaved: () => void;
  onCancel: () => void;
};

// «Представься»: имя и e-mail подпишут версии, которые уйдут в репозиторий. Без
// них сервер не подключает репозиторий и не клонирует (profile_required).
export const ProfileStep = ({ onSaved, onCancel }: ProfileStepProps) => {
  const { t } = useTranslation("gitRemote");
  const profileQuery = useProfile();
  return (
    <div className="flex flex-col" style={{ gap: 12 }}>
      {profileQuery.isError && !profileQuery.data ? (
        <Notice
          tone="err"
          role="alert"
          text={describeGitError(
            profileQuery.error,
            t("connect.profileFailed"),
          )}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void profileQuery.refetch();
              }}
            >
              {t("connect.retry")}
            </button>
          }
        />
      ) : profileQuery.data ? (
        <ProfileForm
          profile={profileQuery.data}
          variant="dialog"
          autoFocus
          allowUnchanged
          submitLabel={t("connect.profileContinue")}
          cancelLabel={t("connect.cancel")}
          onCancel={onCancel}
          onSaved={() => {
            onSaved();
          }}
        />
      ) : (
        <Spinner size="sm" />
      )}
    </div>
  );
};
