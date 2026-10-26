import { describe, expect, it } from "vitest";
import { GIT_PROVIDERS } from "@entities/git-remote";
import {
  GIT_BLOCKED_REASONS,
  GIT_SYNC_OUTCOMES,
  GIT_UI_STATES,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { KEY_STEPS, TOKEN_STEPS, USER_KEY_STEPS } from "../lib/providerHelp";
import { CHECK_ROWS } from "./probeOutcome";
import { COPIED_ISSUE_CODES } from "./issueCopy";

// Ключи, которые собираются из кода при показе, статическая проверка i18n не
// видит. Здесь убеждаемся, что для каждого есть текст на обоих языках.
const ISSUE_ACTIONS = [
  "retry",
  "back_to_repo",
  "back_to_access",
  "updateAccess",
  "review_host_key",
  "review_certificate",
  "close",
];

const TOKEN_ERROR_CODES = [
  "generic",
  "auth_failed",
  "tls_untrusted_ca",
  "tls_pin_mismatch",
  "tls_error",
  "offline",
  "timeout",
  "rate_limited",
  "sso_required",
];

const dynamicKeys = (): string[] => {
  const keys: string[] = [];
  for (const code of COPIED_ISSUE_CODES) {
    keys.push(`gitRemote:issue.${code}.title`, `gitRemote:issue.${code}.hint`);
  }
  for (const action of ISSUE_ACTIONS)
    keys.push(`gitRemote:issue.actions.${action}`);
  for (const id of CHECK_ROWS) keys.push(`gitRemote:check.${id}`);
  for (const variant of ["empty", "same", "new"]) {
    keys.push(
      `gitRemote:result.ready.${variant}.title`,
      `gitRemote:result.ready.${variant}.text`,
    );
  }
  // Мастер клонирования: фазы, итоги доступа и состав собираются из кода.
  for (const phase of [
    "connect",
    "download",
    "downloadBundle",
    "verify",
    "register",
  ]) {
    keys.push(`gitRemote:clone.progress.phase.${phase}`);
  }
  for (const access of ["full", "read_only", "files_only"]) {
    keys.push(
      `gitRemote:clone.progress.access.${access}`,
      `gitRemote:clone.source.verdict.${access}`,
    );
  }
  for (const staffing of ["solo", "team"])
    keys.push(`gitRemote:clone.source.found.staffing_${staffing}`);
  for (const step of ["source", "folder", "progress"])
    keys.push(`gitRemote:clone.steps.${step}`);
  for (const kind of ["https", "http", "ssh", "file"])
    keys.push(`gitRemote:urlKind.${kind}`);
  for (const provider of GIT_PROVIDERS) {
    keys.push(`gitRemote:provider.${provider}`);
    for (const step of TOKEN_STEPS[provider]) {
      keys.push(`gitAccess:help.${provider}.token.${step}`);
    }
    for (const step of KEY_STEPS[provider]) {
      keys.push(`gitAccess:help.${provider}.key.${step}`);
    }
    for (const step of USER_KEY_STEPS[provider]) {
      keys.push(`gitAccess:help.${provider}.userKey.${step}`);
    }
    keys.push(
      `gitRemote:providerPicker.option.${provider}`,
      `gitAccess:servers.detectedBy.${provider === "other" ? "unknown" : "host"}`,
    );
  }
  // Определение типа сервера, подсказки по токену и ключу, проверка токена.
  for (const how of ["override", "host", "api", "unknown"]) {
    keys.push(`gitRemote:providerChip.detectedBy.${how}`);
    keys.push(`gitAccess:servers.detectedBy.${how}`);
  }
  for (const step of ["create", "copy", "paste"]) {
    keys.push(
      `gitAccess:tokenLink.helper.${step}.title`,
      `gitAccess:tokenLink.helper.${step}.text`,
    );
  }
  for (const provider of ["github", "gitlab", "gitlabNew"]) {
    keys.push(
      `gitAccess:tokenLink.fallback.${provider}.lead`,
      `gitAccess:tokenLink.fallback.${provider}.link`,
    );
  }
  for (const kind of [
    "sufficient",
    "too_narrow",
    "too_broad",
    "unknown",
    "expired",
  ]) {
    keys.push(
      `gitAccess:tokenCheck.${kind}.title`,
      `gitAccess:tokenCheck.${kind}.text`,
    );
  }
  for (const code of TOKEN_ERROR_CODES) {
    keys.push(`gitAccess:tokenCheck.error.${code}.title`);
    if (code !== "generic")
      keys.push(`gitAccess:tokenCheck.error.${code}.text`);
  }
  for (const scope of ["deploy", "user"]) {
    keys.push(
      `gitAccess:ssh.scope.${scope}`,
      `gitAccess:ssh.scope.${scope}Hint`,
    );
  }
  for (const choice of ["ca", "pin"])
    keys.push(`gitAccess:tls.choice.${choice}`);
  for (const problem of ["private_key", "not_pem", "too_large"]) {
    keys.push(`gitAccess:tls.ca.problem.${problem}`);
  }
  for (const method of ["pat", "ssh", "none"])
    keys.push(`gitAccess:method.${method}`);
  for (const code of [
    "token_expired",
    "token_insufficient_scope",
    "tls_untrusted_ca",
    "tls_pin_mismatch",
    "provider_unknown",
  ]) {
    keys.push(`gitRemote:issue.${code}.title`, `gitRemote:issue.${code}.hint`);
  }
  for (const status of ["unverified", "ok", "auth_failed", "unreadable"]) {
    keys.push(`gitRemote:credentialStatus.${status}`);
  }
  for (const provider of [
    "yandex_disk",
    "dropbox",
    "syncthing",
    "onedrive",
    "google_drive",
    "icloud",
    "nextcloud",
    "unknown",
  ]) {
    keys.push(`gitAccess:sharedProvider.${provider}`);
  }
  // Настройки проекта и раздел доступа берут состояния, причины и итоги из gitSync.
  for (const state of GIT_UI_STATES) keys.push(`gitSync:state.${state}`);
  for (const reason of GIT_BLOCKED_REASONS) {
    if (reason !== "remote_schema_newer")
      keys.push(`gitSync:blocked.${reason}`);
  }
  for (const outcome of GIT_SYNC_OUTCOMES)
    keys.push(`gitSync:outcome.${outcome}`);
  for (const kind of ["pat", "ssh_key"])
    keys.push(`gitRemote:credentialKind.${kind}`);
  for (const unit of ["minutes", "hours"]) {
    keys.push(`gitRemote:settings.interval.${unit}`);
  }
  return keys;
};

describe("тексты, ключи которых собираются в коде", () => {
  it.each(["ru", "en"])("%s: у каждого ключа есть перевод", (lng) => {
    const missing = dynamicKeys().filter((key) => !i18n.exists(key, { lng }));
    expect(missing).toEqual([]);
  });
});
