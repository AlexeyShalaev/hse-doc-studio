import { useThemeStore } from "@shared/lib";

import type { Theme } from "@shared/lib";

const THEMES: readonly Theme[] = ["system", "dark", "light", "blueprint"];

const isTheme = (value: unknown): value is Theme =>
  typeof value === "string" && (THEMES as readonly string[]).includes(value);

// Apply the client-side effect of an app-control agent tool. The backend tool
// only persists the change server-side (e.g. set_theme writes app settings), so
// the live UI won't move unless we mirror it into the client store the UI reads.
// Returns true when a known effect was applied.
export const applyAgentToolEffect = (
  name: string,
  args: Record<string, unknown>,
): boolean => {
  if (name === "set_theme" && isTheme(args.theme)) {
    useThemeStore.getState().setTheme(args.theme);
    return true;
  }
  return false;
};
