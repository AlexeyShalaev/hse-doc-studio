import { describe, expect, it } from "vitest";
import { GIT_PROVIDERS } from "@entities/git-remote";
import {
  GIT_BLOCKED_REASONS,
  GIT_SYNC_OUTCOMES,
  GIT_UI_STATES,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { KEY_STEPS, TOKEN_STEPS } from "../lib/providerHelp";
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
  "close",
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
  }
  for (const method of ["pat", "ssh"]) keys.push(`gitAccess:method.${method}`);
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
