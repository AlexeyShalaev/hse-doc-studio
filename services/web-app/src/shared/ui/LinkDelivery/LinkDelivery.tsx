import { MailX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CopyField } from "../CopyField";

// Ссылка вместо письма. Без SMTP установка ничего не отправляет, поэтому везде,
// где ушло бы письмо (подтверждение, сброс пароля, приглашение), ссылку
// показывают на экране и человек копирует её сам.

export type LinkDeliveryProps = {
  link: string;
  /** Что за ссылка: подставляется в подпись и пояснение. */
  kind: "verify" | "reset" | "invite";
  /** Одноразовую ссылку второй раз не покажут. */
  once?: boolean;
  className?: string;
};

export const LinkDelivery = ({
  link,
  kind,
  once = false,
  className,
}: LinkDeliveryProps) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <div
      data-testid="link-delivery"
      data-kind={kind}
      className={className}
      style={{
        border: "1px dashed var(--line-strong, var(--line))",
        borderRadius: "var(--r-3)",
        background: "var(--bg-2, transparent)",
        padding: "0.75rem 0.875rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        <MailX
          size="0.9375rem"
          aria-hidden="true"
          style={{ color: "var(--fg-2)", flexShrink: 0 }}
        />
        <strong style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
          {t("linkDelivery.title")}
        </strong>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: "0.78125rem",
          lineHeight: 1.5,
          color: "var(--fg-2)",
        }}
      >
        {t(`linkDelivery.kinds.${kind}`)}
        {once ? ` ${t("linkDelivery.once")}` : ""}
      </p>
      <CopyField value={link} label={t(`linkDelivery.labels.${kind}`)} />
    </div>
  );
};

LinkDelivery.displayName = "LinkDelivery";
