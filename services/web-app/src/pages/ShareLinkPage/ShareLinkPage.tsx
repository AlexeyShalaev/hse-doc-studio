import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  useOpenShareLink,
  useShareLinkPreview,
  type OpenShareLinkResponse,
} from "@entities/share-link";
import { sessionKeys, useBootstrap } from "@entities/session";
import { failureCode } from "@shared/api";
import { i18n } from "@shared/lib";
import { ShareLinkView } from "./ShareLinkView";

const landingPath = (opened: OpenShareLinkResponse): string =>
  opened.landing === "view"
    ? `/projects/${opened.project_id}/view`
    : `/projects/${opened.project_id}`;

/** `/s/:token`: превью ссылки, пароль, имя гостя, вход и переход в проект (10.3). */
export const ShareLinkPage = () => {
  const { t } = useTranslation("guest");
  const { token = "" } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const user = useBootstrap().data?.user ?? null;
  const preview = useShareLinkPreview(token);
  const open = useOpenShareLink(token);
  const [error, setError] = useState<string | null>(null);
  const [needName, setNeedName] = useState(false);
  const loginHref = `/login?next=${encodeURIComponent(`/s/${token}`)}`;

  return (
    <ShareLinkView
      status={preview.data ? "ready" : preview.isError ? "error" : "loading"}
      preview={preview.data ?? null}
      signedInName={user?.name ?? null}
      needName={needName}
      pending={open.isPending}
      error={error}
      loginHref={loginHref}
      onOpen={({ password, guestName }) => {
        setError(null);
        open.mutate(
          { password, guest_name: guestName },
          {
            onSuccess: (opened) => {
              // Токен уходит из адресной строки и истории (T2): страница ссылки заменяется проектом.
              window.history.replaceState(null, "", landingPath(opened));
              void client
                .invalidateQueries({ queryKey: sessionKeys.bootstrap() })
                .then(() => navigate(landingPath(opened), { replace: true }));
            },
            onError: (failure) => {
              const code = failureCode(failure);
              if (code === "guest_name_required") {
                setNeedName(true);
                setError(t("page.nameRequired"));
                return;
              }
              if (code === "link_login_required") {
                void navigate(loginHref);
                return;
              }
              if (code === "link_inactive") {
                void preview.refetch();
                return;
              }
              if (code === "link_password_wrong") {
                setError(t("page.passwordWrong"));
                return;
              }
              setError(
                i18n.exists(`errors:code.${code}`)
                  ? i18n.t(`errors:code.${code}`)
                  : t("page.failed"),
              );
            },
          },
        );
      }}
    />
  );
};
