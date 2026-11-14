import { useCallback, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { useIsPhoneWidth } from "@shared/lib";
import {
  MAIL_LOG_LIST,
  isMailLogNotFound,
  useMailLogEntry,
  useResendMail,
} from "../api/mailLogQueries";
import type { MailLogEntry } from "../api/schemas";
import { useMinuteNow } from "../lib/when";
import {
  MailLogCardView,
  type MailLogCardState,
  type MailResendNotice,
} from "./MailLogCardView";
import { useBlockedText, useReasonText } from "./labels";
import "./mailLog.css";

export type MailLogCardProps = {
  /** Письмо из `?mail=<id>`; null: карточка закрыта. */
  id: number | null;
  /** Строка списка, если письмо на загруженных страницах: шапку можно показать до ответа. */
  row: MailLogEntry | null;
  /** Закрыть карточку: убирает `?mail` из адреса. */
  onClose: () => void;
  /** Открыть другое письмо журнала (исходное или повтор). */
  onOpen?: ((id: number) => void) | undefined;
};

/** Параметры журнала в адресе: переход из карточки к новому условию снимает все прежние. */
const LIST_KEYS = ["q", "page", "mail", ...Object.keys(MAIL_LOG_LIST.filters)];

/**
 * Карточка письма (docs/design/mail-log.md, 4.2): панель справа по `?mail=<id>`, на телефоне
 * шторка снизу. Пока сервер отвечает, шапка и сведения берутся из строки списка.
 */
export const MailLogCard = ({
  id,
  row,
  onClose,
  onOpen,
}: MailLogCardProps): ReactNode => {
  const { t } = useTranslation("adminMail");
  const query = useMailLogEntry(id);
  const resend = useResendMail();
  const reasonText = useReasonText();
  const blockedText = useBlockedText();
  // Плашка итога относится к одному письму: другое письмо открывается без неё.
  const [result, setResult] = useState<{
    id: number;
    notice: MailResendNotice;
  } | null>(null);
  const notice = result !== null && result.id === id ? result.notice : null;
  const setNotice = useCallback(
    (next: MailResendNotice) => {
      if (id !== null) setResult({ id, notice: next });
    },
    [id],
  );

  const doResend = useCallback(() => {
    if (id === null) return;
    resend.mutate(id, {
      onSuccess: (result) => {
        if (result.outcome === "sent") {
          setNotice({ tone: "info", text: t("resend.done.sent") });
        } else if (result.outcome === "retrying") {
          setNotice({ tone: "warn", text: t("resend.done.retrying") });
        } else if (result.outcome === "failed") {
          setNotice({
            tone: "err",
            text: t("resend.done.failed", {
              reason: result.reason ? reasonText(result.reason) : "",
            }),
          });
        } else {
          setNotice({
            tone: "warn",
            text: t("resend.done.blocked", {
              reason: blockedText(result.blocked ?? "unknown"),
            }),
          });
        }
      },
      onError: () => {
        setNotice({ tone: "err", text: t("resend.failed") });
      },
    });
  }, [id, resend, t, reasonText, blockedText, setNotice]);
  const phone = useIsPhoneWidth();
  const now = useMinuteNow();
  const [, setParams] = useSearchParams();

  /** Журнал с одним условием вместо прежних; карточка закрывается тем же переходом. */
  const showOnly = useCallback(
    (patch: Record<string, string>) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        for (const key of LIST_KEYS) next.delete(key);
        for (const [key, value] of Object.entries(patch)) next.set(key, value);
        return next;
      });
    },
    [setParams],
  );

  const detail = query.data ?? null;
  const entry = detail?.entry ?? (row?.id === id ? row : null);
  const state: MailLogCardState =
    query.isError && isMailLogNotFound(query.error)
      ? "not_found"
      : detail
        ? "ready"
        : query.isError
          ? "error"
          : "loading";

  return (
    <Dialog.Root
      open={id !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="ml-card-scrim" />
        <Dialog.Content
          className="ml-card"
          data-form={phone ? "sheet" : "drawer"}
          data-testid="mail-card"
          aria-describedby={undefined}
        >
          {id !== null && (
            <MailLogCardView
              entry={entry}
              detail={detail}
              state={state}
              now={now}
              retrying={query.isFetching}
              onRetry={() => {
                void query.refetch();
              }}
              onClose={onClose}
              onShowRecipient={(e) => {
                showOnly(
                  e.to_user
                    ? { recipient_id: e.to_user.id }
                    : { recipient: e.to_email },
                );
              }}
              onShowProject={(projectId) => {
                showOnly({ project_id: projectId });
              }}
              Title={Dialog.Title}
              onResend={doResend}
              resending={resend.isPending}
              resendNotice={notice}
              onOpenEntry={onOpen}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
