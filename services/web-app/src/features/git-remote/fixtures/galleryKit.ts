import {
  parseRemoteUrl,
  type ParseRemoteUrlResult,
} from "../lib/parseRemoteUrl";
import type { GitContents } from "@entities/git-sync";
import type { FolderInspection } from "../ui/clone/CloneFolderStep";

// Общее для записей галереи шагов подключения и клонирования.

export const noop = (): void => undefined;

export const parse = (value: string): ParseRemoteUrlResult =>
  parseRemoteUrl(value, { allow_local: true });

export const urlOf = (value: string) => {
  const parsed = parse(value);
  if (!parsed.ok) throw new Error(`gallery url is invalid: ${value}`);
  return parsed.url;
};

export type RepoSetup = {
  url: string;
  branch?: string;
  tokenStripped?: boolean;
  ndaRequired?: boolean;
  sharedFolder?: { provider: string } | null;
  contents?: GitContents | undefined;
  contentsState?: "loading" | "error";
};

export type FolderSetup = {
  name?: string;
  folder?: string;
  inspection: FolderInspection;
  /** Код отказа запуска, который относится к папке: текст берётся из словаря ошибок. */
  folderErrorCode?: string;
  /** Общий отказ запуска: стандартный текст мастера. */
  startFailed?: boolean;
  isStarting?: boolean;
};
