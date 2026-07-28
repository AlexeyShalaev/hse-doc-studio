import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ExternalLink } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useEditors } from "../api/systemQueries";
import { openInEditor } from "../lib/openInEditor";
import { EditorIcon } from "./EditorIcon";

export type OpenFolderInEditorProps = {
  // Absolute path of the folder or file to open. Disabled when missing.
  path: string | null | undefined;
};

// A trigger button with an editor-picker dropdown that opens `path` in the
// chosen external editor (line=null → no `:1` anchor, so a directory opens as a
// workspace and a file opens directly). Mirrors the same control in the
// document tabs / pack view; reuses `useEditors` + `openInEditor`.
export const OpenFolderInEditor = ({ path }: OpenFolderInEditorProps) => {
  const { t } = useTranslation("entitiesMisc");
  const { data: editorsData } = useEditors();
  const editors = (editorsData?.editors ?? []).filter((e) => e.available);
  const hasAnyEditor = editors.length > 0;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="btn tt"
          data-tt={
            hasAnyEditor
              ? t("openFolder.openInEditor")
              : t("openFolder.noEditors")
          }
          disabled={!hasAnyEditor || !path}
        >
          <ExternalLink size={12} />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className={clsx(
            // z-[200] (matches the app's other body-portaled popovers) so the
            // editor picker sits above the settings overlay (z-90) and Radix
            // modals (z-101/102) when opened from inside one.
            "z-[200] min-w-[14rem] overflow-hidden rounded-r-3 border border-border bg-bg-1",
            "shadow-elev-pop",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
            "origin-top-right",
          )}
          sideOffset={6}
          align="end"
        >
          <div
            className="label-up dimmer"
            style={{
              padding: "8px 12px 6px",
              fontSize: 9.5,
              letterSpacing: "0.1em",
            }}
          >
            {t("openFolder.openInEditor")}
          </div>
          <div className="divider" style={{ marginBottom: 4 }} />
          {editors.map((e) => (
            <DropdownMenu.Item
              key={e.id}
              className={clsx(
                "group relative flex cursor-pointer select-none items-center gap-3 outline-none",
                "transition-colors",
                "focus:bg-bg-hover",
              )}
              style={{ padding: "8px 12px" }}
              onSelect={() => {
                if (path) openInEditor(e.scheme, path, null);
              }}
            >
              <div
                className="flex items-center justify-center shrink-0"
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  background: "var(--bg-2)",
                  border: "1px solid var(--border)",
                  color: "var(--fg-0)",
                }}
              >
                <EditorIcon editorId={e.id} size={15} />
              </div>
              <div className="flex flex-col min-w-0" style={{ gap: 1 }}>
                <span
                  className="text-fg-0 group-focus:text-fg-0"
                  style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.2 }}
                >
                  {e.label}
                </span>
                <span
                  className="mono dimmer"
                  style={{ fontSize: 10, lineHeight: 1.2 }}
                >
                  {e.scheme}://
                </span>
              </div>
              <ExternalLink
                size={11}
                className="ml-auto shrink-0 text-fg-3 opacity-0 transition-opacity group-focus:opacity-100"
              />
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
};

OpenFolderInEditor.displayName = "OpenFolderInEditor";
