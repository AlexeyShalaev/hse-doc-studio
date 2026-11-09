import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Copy, Download, ExternalLink, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ImageOverlay, ReleaseEntry, SystemInfo } from "@entities/system";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { useSelfUpdate } from "../model/useSelfUpdate";
import { ImageOverlaysNotice } from "./ImageOverlaysNotice";

const updateCommand = (mode: SystemInfo["deployment_mode"] | null): string =>
  mode === "native"
    ? "git pull"
    : "docker compose pull && docker compose up -d";

export type ChangelogModalProps = {
  open: boolean;
  onClose: () => void;
  release: ReleaseEntry | null;
  version: string | null;
  deploymentMode: SystemInfo["deployment_mode"] | null;
  canSelfUpdate: boolean;
  /** Repo URL for the "open on GitHub" link; the tag is derived from `version`. */
  sourceUrl: string | null;
  /** Папки хоста поверх каталогов образа: что с ними станет при обновлении. */
  overlays?: ImageOverlay[];
};

export const ChangelogModal = ({
  open,
  onClose,
  release,
  version,
  deploymentMode,
  canSelfUpdate,
  sourceUrl,
  overlays = [],
}: ChangelogModalProps) => {
  const { t } = useTranslation("checkUpdate");
  const command = updateCommand(deploymentMode);
  const selfUpdate = useSelfUpdate();
  const releaseUrl =
    sourceUrl && version ? `${sourceUrl}/releases/tag/v${version}` : null;

  // One-click is offered only when the backend says it can update itself and we
  // know the target version; otherwise (and after a failed attempt) we fall
  // back to the manual copy-command.
  const showOneClick =
    canSelfUpdate && version !== null && selfUpdate.status !== "failed";

  const handleCopy = () => {
    void navigator.clipboard.writeText(command).then(() => {
      toast.success(t("manual.commandCopied"));
    });
  };

  const handleSelfUpdate = () => {
    if (version) selfUpdate.start(version);
  };

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(o) => {
        if (!o && !selfUpdate.isBusy) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/2 z-[102] -translate-x-1/2 -translate-y-1/2"
          style={{ width: "38.75rem", maxWidth: "calc(100vw - 2rem)" }}
        >
          <DialogPrimitive.Title className="sr-only">
            {t("modal.title")}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            {t("modal.description")}
          </DialogPrimitive.Description>

          <div
            className="flex items-center justify-between"
            style={{
              padding: "0.75rem 1.125rem",
              borderBottom: "1px solid var(--border)",
              gap: "0.75rem",
            }}
          >
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              <Sparkles size="0.875rem" style={{ color: "var(--accent)" }} />
              <h3 style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0 }}>
                {t("modal.title")}
              </h3>
              {version && (
                <span
                  className="mono"
                  style={{
                    fontSize: "0.625rem",
                    padding: "1px 0.375rem",
                    borderRadius: "0.1875rem",
                    background: "var(--accent)",
                    color: "var(--bg-0)",
                  }}
                >
                  v{version}
                </span>
              )}
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              disabled={selfUpdate.isBusy}
              title={t("modal.close")}
            >
              <X size="0.875rem" />
            </button>
          </div>

          <div
            style={{
              padding: "1rem",
              maxHeight: "22.5rem",
              overflowY: "auto",
              fontSize: "0.78125rem",
              lineHeight: 1.5,
              wordBreak: "break-word",
            }}
          >
            {release && release.notes.length > 0 ? (
              <>
                {release.date && (
                  <div
                    className="dim"
                    style={{ fontSize: "0.6875rem", marginBottom: "0.5rem" }}
                  >
                    {release.date}
                  </div>
                )}
                <ul
                  className="flex flex-col"
                  style={{
                    gap: "0.375rem",
                    margin: 0,
                    paddingLeft: "1.125rem",
                  }}
                >
                  {release.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </>
            ) : (
              <span className="dim">{t("modal.emptyBody")}</span>
            )}
          </div>

          <div
            className="flex flex-col"
            style={{
              gap: "0.5rem",
              padding: "0.75rem 1.125rem",
              borderTop: "1px solid var(--border)",
            }}
          >
            {showOneClick ? (
              <>
                <span className="dim" style={{ fontSize: "0.6875rem" }}>
                  {selfUpdate.status === "done"
                    ? t("oneClick.done")
                    : selfUpdate.isBusy
                      ? t("oneClick.busy")
                      : t("oneClick.hint")}
                </span>
                <ImageOverlaysNotice overlays={overlays} />
                <button
                  type="button"
                  className="btn primary flex items-center justify-center"
                  style={{ gap: "0.375rem" }}
                  onClick={handleSelfUpdate}
                  disabled={selfUpdate.isBusy || selfUpdate.status === "done"}
                >
                  {selfUpdate.isBusy || selfUpdate.status === "done" ? (
                    <>
                      <Spinner size="sm" />
                      {t("oneClick.updating")}
                    </>
                  ) : (
                    <>
                      <Download size="0.75rem" />
                      {t("oneClick.updateTo", { version })}
                    </>
                  )}
                </button>
              </>
            ) : (
              <>
                {selfUpdate.status === "failed" && selfUpdate.error && (
                  <span
                    style={{ fontSize: "0.6875rem", color: "var(--c-warn)" }}
                  >
                    {selfUpdate.error}
                  </span>
                )}
                <span className="dim" style={{ fontSize: "0.6875rem" }}>
                  {t("manual.instructions")}
                </span>
                <div
                  className="flex items-center justify-between"
                  style={{
                    gap: "0.5rem",
                    padding: "0.5rem 0.625rem",
                    borderRadius: "0.375rem",
                    background: "var(--bg-0)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <code
                    className="mono"
                    style={{ fontSize: "0.71875rem", wordBreak: "break-all" }}
                  >
                    {command}
                  </code>
                  <button
                    type="button"
                    className="btn xs"
                    onClick={handleCopy}
                    title={t("manual.copyCommand")}
                  >
                    <Copy size="0.6875rem" />
                  </button>
                </div>
              </>
            )}
            {releaseUrl && (
              <a
                href={releaseUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="flex items-center"
                style={{
                  gap: "0.375rem",
                  fontSize: "0.71875rem",
                  color: "var(--accent)",
                }}
              >
                <ExternalLink size="0.6875rem" />
                {t("modal.openOnGithub")}
              </a>
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
