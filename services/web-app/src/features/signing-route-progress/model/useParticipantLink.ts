import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  signingPagePath,
  useSigningParticipantLink,
} from "@entities/signing-route";
import { toast } from "@shared/lib";
import { absoluteUrl, copyText } from "../lib/format";
import { useErrorText } from "./useErrorText";

/** Кому копируем ссылку: участник маршрута по id и его состояние. */
export type LinkTarget = { id: string; state: string };

/**
 * «Скопировать ссылку» подписанту (раздел 6.5): участнику адрес его страницы подписи, приглашённому
 * новая ссылка приглашения от сервера. Не вышло положить в буфер: ссылка остаётся в `shown`, чтобы
 * показать её под человеком и скопировать руками.
 */
export const useParticipantLink = (projectId: string, routeId: string) => {
  const { t } = useTranslation("signingProgress");
  const errorText = useErrorText();
  const link = useSigningParticipantLink(projectId, routeId);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [shown, setShown] = useState<{
    participantId: string;
    url: string;
  } | null>(null);

  const deliver = async (person: LinkTarget, url: string, ok: string) => {
    if (await copyText(url)) {
      setShown(null);
      toast.success(ok);
    } else {
      setShown({ participantId: person.id, url });
      toast.error(t("toast.copyFailed"));
    }
  };

  // Участнику ссылка на его страницу подписи: адрес известен и так, запрос не нужен.
  // Приглашённому нужна ссылка приглашения: её даёт сервер, каждый раз новую (секрет хранится
  // хэшем). Это не напоминание: пауз нет, в маршруте ничего не меняется (5.7).
  const copyLink = (person: LinkTarget) => {
    if (person.state !== "invited") {
      void deliver(
        person,
        absoluteUrl(signingPagePath(projectId, routeId)),
        t("toast.copied"),
      );
      return;
    }
    setPendingId(person.id);
    link.mutate(person.id, {
      onSuccess: (reply) => {
        void deliver(
          person,
          absoluteUrl(reply.link),
          reply.kind === "invitation"
            ? t("toast.inviteCopied")
            : reply.kind === "inbox"
              ? t("toast.inboxCopied")
              : t("toast.copied"),
        );
      },
      onError: (error) => {
        toast.error(errorText(error));
      },
      onSettled: () => {
        setPendingId(null);
      },
    });
  };

  return { pendingId, setPendingId, shown, deliver, copyLink };
};
