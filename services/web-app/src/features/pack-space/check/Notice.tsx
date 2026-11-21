import type { ReactNode } from "react";

/** Плашка «Проверки»: подсказка (`status`) или ошибка (`alert`), необязательное действие. */
export const Notice = ({
  tone = "info",
  title,
  children,
  actions,
}: {
  tone?: "info" | "error";
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) => (
  <div
    className="sp-ck-notice"
    data-tone={tone}
    role={tone === "error" ? "alert" : "status"}
  >
    <p className="sp-ck-notice-title">{title}</p>
    {children ? <p>{children}</p> : null}
    {actions ? <div className="sp-ck-actions">{actions}</div> : null}
  </div>
);
