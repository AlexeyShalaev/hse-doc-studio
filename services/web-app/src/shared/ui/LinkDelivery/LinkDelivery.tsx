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
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div className="flex items-center" style={{ gap: 8 }}>
        <MailX
          size={15}
          aria-hidden="true"
          style={{ color: "var(--fg-2)", flexShrink: 0 }}
        />
        <strong style={{ fontSize: 12.5, fontWeight: 600 }}>
          {t("linkDelivery.title")}
        </strong>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 12.5,
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
