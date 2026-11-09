import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { failureCode } from "@shared/api";
import { safeNextPath, useBootstrap } from "@entities/session";
import {
  useAcceptInvitationByToken,
  useInvitationPreview,
} from "@entities/invitation";
import {
  ProjectInviteView,
  type ProjectInviteState,
} from "./ProjectInviteView";

/**
 * Ссылка из письма-приглашения: карточка, вход или регистрация, «Принять».
 * `?next=` (только путь этого же сайта) ведёт после «Принять» туда, откуда пригласили:
 * подписанта маршрута на страницу подписи (docs/design/signing-route.md, 6.5). Вход и
 * регистрация возвращают на эту же страницу с тем же `next`.
 */
export const ProjectInvitePage = () => {
  const { token = "" } = useParams<{ token: string }>();
  const [params] = useSearchParams();
  const next = safeNextPath(params.get("next"), "");
  const navigate = useNavigate();
  const boot = useBootstrap().data;
  const preview = useInvitationPreview(token);
  const accept = useAcceptInvitationByToken();
  const [mismatch, setMismatch] = useState(false);
  const signedInAs = boot?.user?.email ?? null;
  const here = `/project-invite/${encodeURIComponent(token)}${
    next ? `?next=${encodeURIComponent(next)}` : ""
  }`;

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
            void navigate(next || `/projects/${inv.project.id}`);
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
        // Без пароля (passkey) человек входит сразу, с паролем после письма: оба пути
        // возвращаются сюда, чтобы принять приглашение и пойти дальше по `next`.
        void navigate(
          `/invite/${encodeURIComponent(registrationToken)}${
            next ? `?next=${encodeURIComponent(here)}` : ""
          }`,
        );
      }}
      onHome={() => {
        void navigate("/");
      }}
    />
  );
};
