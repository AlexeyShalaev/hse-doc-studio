import { useCallback, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useSearchParams } from "react-router";
import { useIsPhoneWidth } from "@shared/lib";
import {
  MAIL_LOG_LIST,
  isMailLogNotFound,
  useMailLogEntry,
} from "../api/mailLogQueries";
import type { MailLogEntry } from "../api/schemas";
import { useMinuteNow } from "../lib/when";
import { MailLogCardView, type MailLogCardState } from "./MailLogCardView";
import "./mailLog.css";

export type MailLogCardProps = {
  /** Письмо из `?mail=<id>`; null: карточка закрыта. */
  id: number | null;
  /** Строка списка, если письмо на загруженных страницах: шапку можно показать до ответа. */
  row: MailLogEntry | null;
  /** Закрыть карточку: убирает `?mail` из адреса. */
  onClose: () => void;
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
}: MailLogCardProps): ReactNode => {
  const query = useMailLogEntry(id);
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
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
