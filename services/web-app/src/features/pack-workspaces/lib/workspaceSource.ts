import type { PackWorkspace } from "@entities/pack-studio";

/** Откуда пространство: адрес репозитория с веткой или папка на диске. */
export const workspaceSource = (workspace: PackWorkspace): string =>
  workspace.kind === "git"
    ? [workspace.url, workspace.base_branch].filter(Boolean).join(" · ")
    : (workspace.folder ?? "");

/** Адрес для людей: без протокола, учётных данных и «.git» на конце. */
export const shortUrl = (url: string): string =>
  url
    .trim()
    .replace(/^[a-z+]+:\/\//i, "")
    .replace(/^[^@/]+@/, "")
    .replace(/\.git$/i, "")
    .replace(/\/$/, "");
