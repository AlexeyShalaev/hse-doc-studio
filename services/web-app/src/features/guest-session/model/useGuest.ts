import { useBootstrap, type GuestInfo } from "@entities/session";

/** Гость по ссылке (без входа) или null: вошедший, аноним и локальная Студия. */
export const useGuest = (): GuestInfo | null => {
  const data = useBootstrap().data;
  if (data?.mode !== "server" || data.user !== null) return null;
  return data.guest ?? null;
};
