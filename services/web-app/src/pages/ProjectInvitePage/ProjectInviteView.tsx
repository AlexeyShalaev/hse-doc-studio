import { MailOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useProjectRoleLabel } from "@entities/project";
import type { ProjectInvitationPreview } from "@entities/invitation";

export type ProjectInviteState =
  | { kind: "loading" }
  | { kind: "error" }
  | {
      kind: "preview";
      preview: ProjectInvitationPreview;
      /** Почта вошедшего, если он вошёл. */
      signedInAs: string | null;
      mismatch: boolean;
      accepted: boolean;
    };

export type ProjectInviteViewProps = {
  state: ProjectInviteState;
  busy?: boolean;
  onAccept: () => void;
  onSignIn: () => void;
  onSignUp: (registrationToken: string) => void;
  onHome: () => void;
};

/** Страница по ссылке из письма (/project-invite/:token, 10.10). */
export const ProjectInviteView = ({
  state,
  busy = false,
  onAccept,
  onSignIn,
  onSignUp,
  onHome,
}: ProjectInviteViewProps) => {
  const { t } = useTranslation("invitations");
  const roleLabel = useProjectRoleLabel();
  if (state.kind === "loading") {
    return (
      <div data-testid="project-invite-page" data-state="loading">
        <Spinner />
      </div>
    );
  }
  const preview = state.kind === "preview" ? state.preview : null;
  const dataState =
    state.kind === "error"
      ? "invalid"
      : preview?.state !== "ok"
        ? (preview?.state ?? "invalid")
        : state.accepted
          ? "accepted"
          : state.mismatch
            ? "email_mismatch"
            : preview.registration_token && !state.signedInAs
              ? "signup"
              : "ok";
  return (
    <section
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="project-invite-page"
      data-state={dataState}
    >
      <div className="flex items-center" style={{ gap: 10 }}>
        <MailOpen size={20} aria-hidden="true" />
        <h1 style={{ margin: 0, fontSize: 20 }}>{t("page.title")}</h1>
      </div>
      {preview?.state === "ok" ? (
        <>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>
            {t("page.lead", {
              actor: preview.inviter_name ?? "",
              project: preview.project_name ?? "",
              role: preview.role ? roleLabel(preview.role) : "",
            })}
          </p>
          {dataState === "accepted" && (
            <Notice tone="info" role="status" text={t("page.accepted")} />
          )}
          {dataState === "email_mismatch" && state.kind === "preview" && (
            <Notice
              tone="warn"
              role="alert"
              text={t("page.mismatch", {
                hint: preview.email_hint ?? "",
                email: state.signedInAs ?? "",
              })}
            />
          )}
          {(dataState === "ok" || dataState === "signup") &&
            state.kind === "preview" &&
            !state.signedInAs && (
              <p className="dim" style={{ margin: 0, fontSize: 12.5 }}>
                {t("page.signInAs", { hint: preview.email_hint ?? "" })}
              </p>
            )}
          <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
            {state.kind === "preview" &&
              state.signedInAs &&
              !state.accepted && (
                <Button
                  type="button"
                  disabled={busy}
                  data-testid="project-invite-accept"
                  onClick={onAccept}
                >
                  {t("page.accept")}
                </Button>
              )}
            {state.kind === "preview" && !state.signedInAs && (
              <>
                {preview.registration_token ? (
                  <Button
                    type="button"
                    data-testid="project-invite-signup"
                    onClick={() => {
                      onSignUp(preview.registration_token ?? "");
                    }}
                  >
                    {t("page.signUp")}
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant={preview.registration_token ? "secondary" : "primary"}
                  data-testid="project-invite-signin"
                  onClick={onSignIn}
                >
                  {t("page.signIn")}
                </Button>
              </>
            )}
            {state.kind === "preview" && (state.mismatch || state.accepted) && (
              <Button type="button" variant="secondary" onClick={onHome}>
                {t("page.home")}
              </Button>
            )}
          </div>
        </>
      ) : (
        <>
          <Notice tone="warn" text={t(`page.state.${dataState}`)} />
          <div>
            <Button type="button" variant="secondary" onClick={onHome}>
              {t("page.home")}
            </Button>
          </div>
        </>
      )}
    </section>
  );
};
