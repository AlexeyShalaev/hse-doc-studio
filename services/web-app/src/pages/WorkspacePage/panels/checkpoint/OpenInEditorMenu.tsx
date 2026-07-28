import { useTranslation } from "react-i18next";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ExternalLink } from "lucide-react";
import { clsx } from "clsx";
import { EditorIcon, openInEditor, type EditorEntry } from "@entities/system";

export type OpenInEditorMenuProps = {
  outputDir: string | null | undefined;
  editors: EditorEntry[];
};

/**
 * Триггер с выбором редактора — зеркало такого же контрола во вкладках
 * документа. Каждый пункт открывает папку с PDF этой сборки (line=null →
 * открывается директория, без якоря `:1`).
 */
export const OpenInEditorMenu = ({
  outputDir,
  editors,
}: OpenInEditorMenuProps) => {
  const { t } = useTranslation("workspace");
  const hasAnyEditor = editors.length > 0;
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="icon-btn sm tt"
          data-tt={
            hasAnyEditor
              ? t("pack.openFolderInEditor")
              : t("pack.noEditorsDetected")
          }
          disabled={!hasAnyEditor || !outputDir}
        >
          <ExternalLink size={11} />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className={clsx(
            "z-50 min-w-[14rem] overflow-hidden rounded-r-3 border border-border bg-bg-1",
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
            {t("pack.openFolderInEditor")}
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
                if (outputDir) openInEditor(e.scheme, outputDir, null);
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
