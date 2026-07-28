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
        <div className="flex items-center justify-end" style={{ gap: 8 }}>
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
            {isPending ? <Spinner size="sm" /> : <RotateCcw size={13} />}
            {t("restore.confirm")}
          </button>
        </div>
      }
    >
      {commit && (
        <div className="flex flex-col" style={{ gap: 12 }}>
          <div
            className="card"
            style={{ padding: 12, background: "var(--bg-2)" }}
          >
            <div style={{ fontSize: 12.5, color: "var(--fg-0)" }}>
              {commit.message}
            </div>
            <div className="dim mono" style={{ fontSize: 10.5, marginTop: 4 }}>
              {commit.short_id} ·{" "}
              {new Date(commit.created_at).toLocaleString(dateLocale)}
            </div>
          </div>
          <div
            className="flex items-start"
            style={{
              gap: 8,
              padding: 12,
              borderRadius: "var(--r-2)",
              background: "var(--accent-soft)",
            }}
          >
            <ShieldCheck
              size={15}
              style={{ color: "var(--accent)", flexShrink: 0, marginTop: 1 }}
            />
            <span
              style={{ fontSize: 11.5, lineHeight: 1.5, color: "var(--fg-1)" }}
            >
              {t("restore.explanation")}
            </span>
          </div>
        </div>
      )}
    </Modal>
  );
};
