import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Copy, Download, ExternalLink, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReleaseEntry, SystemInfo } from "@entities/system";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { useSelfUpdate } from "../model/useSelfUpdate";

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
};

export const ChangelogModal = ({
  open,
  onClose,
  release,
  version,
  deploymentMode,
  canSelfUpdate,
  sourceUrl,
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
          style={{ width: 620, maxWidth: "calc(100vw - 32px)" }}
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
              padding: "12px 18px",
              borderBottom: "1px solid var(--border)",
              gap: 12,
            }}
          >
            <div className="flex items-center" style={{ gap: 8 }}>
              <Sparkles size={14} style={{ color: "var(--accent)" }} />
              <h3 style={{ fontSize: 14, fontWeight: 600, margin: 0 }}>
                {t("modal.title")}
              </h3>
              {version && (
                <span
                  className="mono"
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 3,
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
              <X size={14} />
            </button>
          </div>

          <div
            style={{
              padding: 16,
              maxHeight: 360,
              overflowY: "auto",
              fontSize: 12.5,
              lineHeight: 1.5,
              wordBreak: "break-word",
            }}
          >
            {release && release.notes.length > 0 ? (
              <>
                {release.date && (
                  <div
                    className="dim"
                    style={{ fontSize: 11, marginBottom: 8 }}
                  >
                    {release.date}
                  </div>
                )}
                <ul
                  className="flex flex-col"
                  style={{ gap: 6, margin: 0, paddingLeft: 18 }}
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
              gap: 8,
              padding: "12px 18px",
              borderTop: "1px solid var(--border)",
            }}
          >
            {showOneClick ? (
              <>
                <span className="dim" style={{ fontSize: 11 }}>
                  {selfUpdate.status === "done"
                    ? t("oneClick.done")
                    : selfUpdate.isBusy
                      ? t("oneClick.busy")
                      : t("oneClick.hint")}
                </span>
                <button
                  type="button"
                  className="btn primary flex items-center justify-center"
                  style={{ gap: 6 }}
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
                      <Download size={12} />
                      {t("oneClick.updateTo", { version })}
                    </>
                  )}
                </button>
              </>
            ) : (
              <>
                {selfUpdate.status === "failed" && selfUpdate.error && (
                  <span style={{ fontSize: 11, color: "var(--c-warn)" }}>
                    {selfUpdate.error}
                  </span>
                )}
                <span className="dim" style={{ fontSize: 11 }}>
                  {t("manual.instructions")}
                </span>
                <div
                  className="flex items-center justify-between"
                  style={{
                    gap: 8,
                    padding: "8px 10px",
                    borderRadius: 6,
                    background: "var(--bg-0)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <code
                    className="mono"
                    style={{ fontSize: 11.5, wordBreak: "break-all" }}
                  >
                    {command}
                  </code>
                  <button
                    type="button"
                    className="btn xs"
                    onClick={handleCopy}
                    title={t("manual.copyCommand")}
                  >
                    <Copy size={11} />
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
                style={{ gap: 6, fontSize: 11.5, color: "var(--accent)" }}
              >
                <ExternalLink size={11} />
                {t("modal.openOnGithub")}
              </a>
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
