import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

// «Технические подробности»: идентификаторы, имена файлов и прочее, что нужно редко и не должно
// стоять на первом экране формы (pack-studio-ux.md, принципы P4 и P5). Свёрнуто по умолчанию.

export type TechDetailsProps = {
  children: ReactNode;
  /** Заголовок вместо «Технические подробности» (например, «Дополнительно» в окне создания). */
  title?: string | undefined;
  open?: boolean | undefined;
  testId?: string | undefined;
};

export const TechDetails = ({
  children,
  title,
  open,
  testId,
}: TechDetailsProps) => {
  const { t } = useTranslation("common");
  return (
    <details className="tech-details" open={open} data-testid={testId}>
      <summary>{title ?? t("techDetails")}</summary>
      <div className="tech-details-body">{children}</div>
    </details>
  );
};
