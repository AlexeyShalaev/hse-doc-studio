import type { ReactNode } from "react";
import { CircleAlert, Info } from "lucide-react";
import "./styles";

type NoticeProps = {
  tone: "error" | "info";
  title: string;
  /** Пояснение под заголовком. */
  children?: ReactNode;
  /** Кнопки и ссылки справа. */
  actions?: ReactNode;
  testId?: string;
};

/** Плашка экрана: ошибка (role="alert") или подсказка (role="status"), действия рядом. */
export const Notice = ({
  tone,
  title,
  children,
  actions,
  testId,
}: NoticeProps) => {
  const Icon = tone === "error" ? CircleAlert : Info;
  return (
    <div
      className="po-notice"
      data-tone={tone}
      role={tone === "error" ? "alert" : "status"}
      data-testid={testId}
    >
      <Icon size="1rem" aria-hidden="true" className="po-notice-icon" />
      <div className="po-notice-text">
        <p className="po-notice-title">{title}</p>
        {children && <p className="po-notice-lead">{children}</p>}
      </div>
      {actions && <div className="po-notice-actions">{actions}</div>}
    </div>
  );
};
