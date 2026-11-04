import { useState } from "react";
import { UserRoundX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ProfileForm, useClearProfile, useProfile } from "@entities/profile";
import { describeGitError } from "@entities/git-sync";
import { toast } from "@shared/lib";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";

// Раздел настроек «Автор версий». Якоря profile, profile-name и profile-email
// нужны поиску по настройкам: он прокручивает к ним и подсвечивает.
export const AuthorProfileSection = () => {
  const { t } = useTranslation("profile");
  const profileQuery = useProfile();
  const clear = useClearProfile();
  // После «Вернуть общую подпись» форму пересоздаём, чтобы поля стали пустыми.
  const [formKey, setFormKey] = useState(0);
  const profile = profileQuery.data;

  const handleReset = () => {
    if (!window.confirm(t("section.resetConfirm"))) return;
    clear.mutate(undefined, {
      onSuccess: () => {
        setFormKey((key) => key + 1);
        toast.success(t("toast.cleared"));
      },
    });
  };

  return (
    <>
      <div
        id="profile"
        className="flex flex-col settings-anchor"
        style={{ gap: "0.25rem", marginBottom: "0.25rem" }}
      >
        <h4 style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}>
          {t("section.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: "0.75rem" }}>
          {t("section.subtitle")}
        </p>
      </div>

      <div
        className="flex flex-col"
        style={{
          gap: "0.875rem",
          paddingBottom: "0.875rem",
          maxWidth: "32.5rem",
        }}
      >
        {profileQuery.isLoading && (
          <div
            className="flex items-center"
            style={{ gap: "0.5rem", fontSize: "0.75rem" }}
            data-testid="profile-loading"
          >
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
          <div
            style={{
              padding: "1rem",
              borderRadius: "var(--r-3)",
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
            }}
          >
            <ProfileForm
              key={formKey}
              profile={profile}
              anchors={{ name: "profile-name", email: "profile-email" }}
              onSaved={() => {
                toast.success(t("toast.saved"));
              }}
              actionsStart={
                profile.is_default ? undefined : (
                  <button
                    type="button"
                    className="btn ghost"
                    disabled={clear.isPending}
                    onClick={handleReset}
                  >
                    <UserRoundX size="0.8125rem" aria-hidden="true" />
                    {t("section.reset")}
                  </button>
                )
              }
            />
          </div>
        )}

        {clear.isError && (
          <Notice
            tone="err"
            role="alert"
            text={describeGitError(clear.error, t("section.resetFailed"))}
          />
        )}
      </div>
    </>
  );
};
