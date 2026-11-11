import type { ReactNode } from "react";
import type { MailLogEntry } from "../api/schemas";

export type MailLogCardProps = {
  /** Письмо из `?mail=<id>`; null: карточка закрыта. */
  id: number | null;
  /** Строка списка, если письмо на загруженных страницах: шапку можно показать до ответа. */
  row: MailLogEntry | null;
  /** Закрыть карточку: убирает `?mail` из адреса. */
  onClose: () => void;
};

/**
 * Карточка письма справа (docs/design/mail-log.md, 4.2). Место под срез W3: список (W2) уже
 * держит открытое письмо в адресе и отдаёт сюда его номер, строку и закрытие. W3 заменяет тело
 * этого компонента, не трогая список: useMailLogEntry(id), сведения, превью, «Что можно сделать».
 */
export const MailLogCard: (props: MailLogCardProps) => ReactNode = () => null;
