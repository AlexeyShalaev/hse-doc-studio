import { useTranslation } from "react-i18next";
import { Compass, X } from "lucide-react";

export type InviteCardProps = {
  onStart: () => void;
  onDismiss: () => void;
};

/** Ненавязчивое приглашение пройти знакомство: карточка в углу, без затемнения. */
export const InviteCard = ({ onStart, onDismiss }: InviteCardProps) => {
  const { t } = useTranslation("onboarding");
  return (
    <aside
      role="status"
      aria-label={t("invite.title")}
      data-testid="onboarding-invite"
      style={{
        position: "fixed",
        right: 16,
        bottom: 40,
        zIndex: 60,
        width: "min(340px, calc(100vw - 32px))",
        background: "var(--bg-1)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-3)",
        boxShadow: "var(--shadow-pop)",
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div className="flex items-start" style={{ gap: 10 }}>
        <Compass
          size={16}
          style={{ color: "var(--accent)", marginTop: 2, flexShrink: 0 }}
        />
        <div className="flex flex-col flex-1" style={{ gap: 4 }}>
          <strong style={{ fontSize: 13, color: "var(--fg-0)" }}>
            {t("invite.title")}
          </strong>
          <span className="dim" style={{ fontSize: 12, lineHeight: 1.45 }}>
            {t("invite.body")}
          </span>
        </div>
        <button
          type="button"
          className="icon-btn"
          aria-label={t("invite.later")}
          onClick={onDismiss}
          style={{ width: 22, height: 22 }}
        >
          <X size={12} />
        </button>
      </div>
      <div className="flex justify-end" style={{ gap: 6 }}>
        <button type="button" className="btn ghost sm" onClick={onDismiss}>
          {t("invite.later")}
        </button>
        <button
          type="button"
          className="btn primary sm"
          onClick={onStart}
          data-testid="onboarding-invite-start"
        >
          {t("invite.start")}
        </button>
      </div>
    </aside>
  );
};
