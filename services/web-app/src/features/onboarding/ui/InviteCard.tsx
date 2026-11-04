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
        right: "1rem",
        bottom: "2.5rem",
        zIndex: 60,
        width: "min(21.25rem, calc(100vw - 2rem))",
        background: "var(--bg-1)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-3)",
        boxShadow: "var(--shadow-pop)",
        padding: "0.875rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <div className="flex items-start" style={{ gap: "0.625rem" }}>
        <Compass
          size="1rem"
          style={{
            color: "var(--accent)",
            marginTop: "0.125rem",
            flexShrink: 0,
          }}
        />
        <div className="flex flex-col flex-1" style={{ gap: "0.25rem" }}>
          <strong style={{ fontSize: "0.8125rem", color: "var(--fg-0)" }}>
            {t("invite.title")}
          </strong>
          <span
            className="dim"
            style={{ fontSize: "0.75rem", lineHeight: 1.45 }}
          >
            {t("invite.body")}
          </span>
        </div>
        <button
          type="button"
          className="icon-btn"
          aria-label={t("invite.later")}
          onClick={onDismiss}
          style={{ width: "1.375rem", height: "1.375rem" }}
        >
          <X size="0.75rem" />
        </button>
      </div>
      <div className="flex justify-end" style={{ gap: "0.375rem" }}>
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
