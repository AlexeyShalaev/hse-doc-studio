import { useTranslation } from "react-i18next";
import type { LinkRole } from "@entities/session";
import { Notice } from "@shared/ui/ConflictKit";

export type LinkAccessBannerProps = {
  label: string;
  role: LinkRole | "owner";
  showSources: boolean;
  /** Гость без входа; вошедшему по ссылке агент доступен. */
  guest: boolean;
};

/** Баннер рабочей области: проект открыт по ссылке, что доступно и что нет (10.4). */
export const LinkAccessBanner = ({
  label,
  role,
  showSources,
  guest,
}: LinkAccessBannerProps) => {
  const { t } = useTranslation("guest");
  const allowedKey =
    role === "reader"
      ? showSources
        ? "readerSources"
        : "reader"
      : role === "reviewer"
        ? "reviewer"
        : "editor";
  const allowed = t(`banner.allowed.${allowedKey}`);
  return (
    <div style={{ padding: "8px 12px" }} data-testid="link-access-banner">
      <Notice
        tone="info"
        role="status"
        text={
          guest
            ? t("banner.text", { label, allowed })
            : t("banner.textUser", { label, allowed })
        }
      />
    </div>
  );
};
