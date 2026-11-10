import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { PenLine } from "lucide-react";
import { HelpAnchor } from "@entities/help";
import type { SigningHold } from "../model/useDocSigningHold";

export type SigningHoldBannerProps = {
  projectId: string;
  hold: SigningHold;
};

/**
 * Плашка редактора документа на подписании (docs/design/signing-route.md, 3.1, 5.5): подписи
 * менять нельзя, правка и пересборка разрешены, но остановят маршрут. Ссылка ведёт к ходу
 * маршрута на точке сдачи.
 */
export const SigningHoldBanner = ({
  projectId,
  hold,
}: SigningHoldBannerProps) => {
  const { t } = useTranslation("signingProgress");
  return (
    <div
      role="status"
      data-testid="signing-hold-banner"
      className="flex items-start"
      style={{
        gap: "0.5rem",
        padding: "0.625rem 1rem",
        background: "var(--bg-1)",
        borderBottom: "1px solid var(--border)",
        borderLeft: "3px solid var(--c-info)",
        fontSize: "0.75rem",
        lineHeight: 1.5,
      }}
    >
      <PenLine
        size="0.875rem"
        aria-hidden="true"
        style={{ color: "var(--c-info)", flexShrink: 0, marginTop: "0.125rem" }}
      />
      <div
        className="flex flex-col"
        style={{ gap: "0.125rem", minWidth: 0, flex: 1 }}
      >
        <span style={{ color: "var(--fg-0)" }}>
          {t("hold.banner", {
            step: hold.step ?? hold.total,
            total: hold.total,
          })}
          {/* «?» плашки: шаг статьи о ходе подписания про правку документа на подписании. */}
          <HelpAnchor article="runbooks/signing-progress" step={4} />
        </span>
        <span className="dim">{t("hold.signatures")}</span>
      </div>
      <Link
        to={`/projects/${encodeURIComponent(projectId)}/submit/cp/${encodeURIComponent(hold.profileId)}`}
        className="btn xs"
        style={{ flexShrink: 0 }}
        data-testid="signing-hold-open"
      >
        {t("hold.open")}
      </Link>
    </div>
  );
};
