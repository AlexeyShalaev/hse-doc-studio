/** Приглашение для пересылки вручную: сообщение и ссылка одним текстом. */
export const invitationText = (message: string | null, link: string) =>
  message ? `${message}\n\n${link}` : link;
