import { useTranslation } from "react-i18next";
import { RotateCcw, ShieldCheck } from "lucide-react";
import { Modal } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag } from "@shared/lib";
import type { VcsCommit } from "@entities/vcs";

export type RestoreConfirmModalProps = {
  commit: VcsCommit | null;
  isPending: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export const RestoreConfirmModal = ({
  commit,
  isPending,
  onClose,
  onConfirm,
}: RestoreConfirmModalProps) => {
  const { t } = useTranslation("vcsHistory");
  const dateLocale = localeTag();
  return (
    <Modal
      isOpen={commit !== null}
      onClose={onClose}
      title={t("restore.title")}
      width={460}
      footer={
        <div
          className="flex items-center justify-end"
          style={{ gap: "0.5rem" }}
        >
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={isPending}
          >
            {t("restore.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? <Spinner size="sm" /> : <RotateCcw size="0.8125rem" />}
            {t("restore.confirm")}
          </button>
        </div>
      }
    >
      {commit && (
        <div className="flex flex-col" style={{ gap: "0.75rem" }}>
          <div
            className="card"
            style={{ padding: "0.75rem", background: "var(--bg-2)" }}
          >
            <div style={{ fontSize: "0.78125rem", color: "var(--fg-0)" }}>
              {commit.message}
            </div>
            <div
              className="dim mono"
              style={{ fontSize: "0.65625rem", marginTop: "0.25rem" }}
            >
              {commit.short_id} ·{" "}
              {new Date(commit.created_at).toLocaleString(dateLocale)}
            </div>
          </div>
          <div
            className="flex items-start"
            style={{
              gap: "0.5rem",
              padding: "0.75rem",
              borderRadius: "var(--r-2)",
              background: "var(--accent-soft)",
            }}
          >
            <ShieldCheck
              size="0.9375rem"
              style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}
            />
            <span
              style={{
                fontSize: "0.71875rem",
                lineHeight: 1.5,
                color: "var(--fg-1)",
              }}
            >
              {t("restore.explanation")}
            </span>
          </div>
        </div>
      )}
    </Modal>
  );
};
