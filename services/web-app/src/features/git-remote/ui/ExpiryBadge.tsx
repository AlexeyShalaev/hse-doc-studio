import { useTranslation } from "react-i18next";
import { credentialExpiry } from "@entities/git-remote";
import { Badge } from "@shared/ui/Badge";
import { formatDate } from "../lib/formatDate";

export type ExpiryBadgeProps = {
  expiresAt: string | null | undefined;
  /** Показывать и «действует до …», когда до срока далеко. */
  showFar?: boolean;
  /** Не рисовать плашку «скоро» и «истёк»: они уже есть рядом (текстовая строка с датой). */
  hideSoon?: boolean;
  now?: number;
};

// Срок токена: далеко виден только как обычный текст, ближе двух недель и после
// срока это плашка. Цвет подкрепляет слова, а не заменяет их.
export const ExpiryBadge = ({
  expiresAt,
  showFar = false,
  hideSoon = false,
  now,
}: ExpiryBadgeProps) => {
  const { t } = useTranslation("gitAccess");
  const expiry = credentialExpiry(expiresAt, now);
  if (expiry.state === "none") return null;
  if (hideSoon && expiry.state !== "ok") {
    return (
      <span
        className="dim"
        style={{ fontSize: 11.5 }}
        data-testid="expiry-date"
      >
        {expiry.state === "expired"
          ? t("expiry.expiredOn", { date: formatDate(expiry.at) })
          : t("expiry.until", { date: formatDate(expiry.at) })}
      </span>
    );
  }
  if (expiry.state === "expired") {
    return (
      <Badge variant="error" data-testid="expiry-badge" data-state="expired">
        {expiry.days === 0
          ? t("expiry.expiredToday")
          : t("expiry.expired", { count: expiry.days })}
      </Badge>
    );
  }
  if (expiry.state === "soon") {
    return (
      <Badge variant="warning" data-testid="expiry-badge" data-state="soon">
        {t("expiry.soon", { count: expiry.days })}
      </Badge>
    );
  }
  if (!showFar) return null;
  return (
    <span
      className="dim"
      style={{ fontSize: 11.5 }}
      data-testid="expiry-badge"
      data-state="ok"
    >
      {t("expiry.until", { date: formatDate(expiry.at) })}
    </span>
  );
};
