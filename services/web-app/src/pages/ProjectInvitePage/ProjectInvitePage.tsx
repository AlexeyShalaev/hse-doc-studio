import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { failureCode } from "@shared/api";
import { useBootstrap } from "@entities/session";
import {
  useAcceptInvitationByToken,
  useInvitationPreview,
} from "@entities/invitation";
import {
  ProjectInviteView,
  type ProjectInviteState,
} from "./ProjectInviteView";

/** Ссылка из письма-приглашения: карточка, вход или регистрация, «Принять». */
export const ProjectInvitePage = () => {
  const { token = "" } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const boot = useBootstrap().data;
  const preview = useInvitationPreview(token);
  const accept = useAcceptInvitationByToken();
  const [mismatch, setMismatch] = useState(false);
  const signedInAs = boot?.user?.email ?? null;
  const here = `/project-invite/${encodeURIComponent(token)}`;

  const state: ProjectInviteState = preview.isError
    ? { kind: "error" }
    : !preview.data
      ? { kind: "loading" }
      : {
          kind: "preview",
          preview: preview.data,
          signedInAs,
          mismatch,
          accepted: accept.isSuccess,
        };

  return (
    <ProjectInviteView
      state={state}
      busy={accept.isPending}
      onAccept={() => {
        accept.mutate(token, {
          onSuccess: (inv) => {
            void navigate(`/projects/${inv.project.id}`);
          },
          onError: (e) => {
            if (failureCode(e) === "invitation_email_mismatch")
              setMismatch(true);
          },
        });
      }}
      onSignIn={() => {
        void navigate(`/login?next=${encodeURIComponent(here)}`);
      }}
      onSignUp={(registrationToken) => {
        void navigate(`/invite/${encodeURIComponent(registrationToken)}`);
      }}
      onHome={() => {
        void navigate("/");
      }}
    />
  );
};
