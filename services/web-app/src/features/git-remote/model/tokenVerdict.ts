import {
  readGitError,
  type GitProviderInfo,
  type GitTlsCertificate,
} from "@entities/git-sync";
import { ApiError } from "@shared/api";
import type { GitCredentialCheck, GitTokenInfo } from "@entities/git-remote";

// Что сказать о токене после проверки: чистые функции без интерфейса. Ответ
// проверки токена (и token_info из проверки адреса) сводится к одному вердикту.

export type TokenVerdict =
  | {
      kind: "sufficient" | "too_narrow" | "too_broad" | "unknown";
      /** null: сервер не дал разобрать токен. */
      info: GitTokenInfo | null;
    }
  | { kind: "expired"; info: GitTokenInfo | null }
  | {
      kind: "error";
      code: string;
      detail: string;
      certificate: GitTlsCertificate | null;
      info: GitTokenInfo | null;
    };

const SUFFICIENCY = ["sufficient", "too_narrow", "too_broad"] as const;

/** Токен принят: хватает ли прав, определяет token_info (его нет, если спросить нечем). */
export const verdictOfCheck = (
  check: Pick<GitCredentialCheck, "token_info">,
): TokenVerdict => {
  const info = check.token_info ?? null;
  const kind = SUFFICIENCY.find((value) => value === info?.sufficiency);
  return { kind: kind ?? "unknown", info };
};

/** Токен без разбора прав, но с известным сроком: этого хватает, чтобы показать «истёк такого-то числа». */
const expiryOnly = (
  expiresAt: string | null | undefined,
): GitTokenInfo | null =>
  expiresAt
    ? {
        login: null,
        scopes: [],
        expires_at: expiresAt,
        sufficiency: "unknown",
        missing: [],
      }
    : null;

/**
 * Вердикт по отказу: проверка токена и проверка адреса отвечают ошибкой с кодом
 * (токен не принят, истёк, сертификат, сеть). `expiresAt` это срок из доступа:
 * ошибка его не несёт.
 */
export const verdictOfError = (
  error: unknown,
  expiresAt?: string | null,
): TokenVerdict => {
  const body = readGitError(error);
  const code =
    body?.code ?? (error instanceof ApiError ? error.code : "git_error");
  if (code === "token_expired") {
    return { kind: "expired", info: expiryOnly(expiresAt) };
  }
  return {
    kind: "error",
    code,
    detail: body?.detail ?? (error instanceof Error ? error.message : ""),
    certificate: body?.certificate ?? null,
    info: null,
  };
};

/** Права токена, которых нет в списке нужных: их показываем при слишком широком доступе. */
export const extraScopes = (
  info: GitTokenInfo | null,
  tooBroad: readonly string[],
): string[] =>
  info ? info.scopes.filter((scope) => tooBroad.includes(scope)) : [];

export type TokenCheckState =
  | { status: "idle" }
  | { status: "checking" }
  | {
      status: "done";
      credentialId: string;
      verdict: TokenVerdict;
      /** Что сервер сказал о себе (версия); null, если проверка не дошла до ответа. */
      provider: GitProviderInfo | null;
    };
