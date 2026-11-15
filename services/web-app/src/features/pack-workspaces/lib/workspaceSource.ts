import type { PackWorkspace } from "@entities/pack-studio";

/** Откуда пространство: адрес репозитория с веткой или папка на диске. */
export const workspaceSource = (workspace: PackWorkspace): string =>
  workspace.kind === "git"
    ? [workspace.url, workspace.base_branch].filter(Boolean).join(" · ")
    : (workspace.folder ?? "");
