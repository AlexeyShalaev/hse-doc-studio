/** Вкладки «Входящих»; выбранная живёт в адресе (`/inbox?tab=signing`). */
export const INBOX_TABS = [
  "all",
  "signing",
  "invitations",
  "requests",
  "transfers",
] as const;
export type InboxTab = (typeof INBOX_TABS)[number];

/** Вкладка из адреса; неизвестная значит «Всё». */
export const inboxTabOf = (value: string | null): InboxTab =>
  INBOX_TABS.find((tab) => tab === value) ?? "all";
