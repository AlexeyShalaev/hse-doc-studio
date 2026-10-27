// Срок действия токена: сколько осталось и что показать. Чистые функции без
// интерфейса; «скоро» это две недели и меньше.

export const EXPIRING_SOON_DAYS = 14;

const DAY_MS = 24 * 60 * 60 * 1000;

export type ExpiryState = "none" | "ok" | "soon" | "expired";

export type CredentialExpiry = {
  state: ExpiryState;
  /** Сколько дней осталось (state ok и soon) или прошло (expired). */
  days: number;
  at: Date | null;
};

export const credentialExpiry = (
  expiresAt: string | null | undefined,
  now: number = Date.now(),
): CredentialExpiry => {
  if (!expiresAt) return { state: "none", days: 0, at: null };
  const at = new Date(expiresAt);
  if (Number.isNaN(at.getTime())) return { state: "none", days: 0, at: null };
  const left = at.getTime() - now;
  if (left <= 0) {
    return {
      state: "expired",
      days: Math.floor((now - at.getTime()) / DAY_MS),
      at,
    };
  }
  const days = Math.ceil(left / DAY_MS);
  return { state: days <= EXPIRING_SOON_DAYS ? "soon" : "ok", days, at };
};

/** Самый срочный срок из нескольких: просрочен, затем скоро, затем остальные. */
export const worstExpiry = (
  values: readonly (string | null | undefined)[],
  now: number = Date.now(),
): CredentialExpiry => {
  const order: Record<ExpiryState, number> = {
    expired: 0,
    soon: 1,
    ok: 2,
    none: 3,
  };
  return values
    .map((value) => credentialExpiry(value, now))
    .reduce<CredentialExpiry>(
      (worst, item) =>
        order[item.state] < order[worst.state] ||
        (item.state === worst.state &&
          item.state !== "none" &&
          item.days < worst.days)
          ? item
          : worst,
      { state: "none", days: 0, at: null },
    );
};
