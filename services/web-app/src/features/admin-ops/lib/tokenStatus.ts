import type { AdminRunnerToken } from "@entities/session";

export type TokenStatus = "active" | "expired" | "exhausted" | "revoked";

export const tokenStatus = (
  token: AdminRunnerToken,
  now: number,
): TokenStatus => {
  if (token.revoked) return "revoked";
  if (token.uses >= token.max_uses) return "exhausted";
  if (token.expires_at !== null && Date.parse(token.expires_at) <= now) {
    return "expired";
  }
  return "active";
};
