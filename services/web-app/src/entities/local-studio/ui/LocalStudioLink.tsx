import type { ReactNode } from "react";
import { Link } from "react-router";
import { Laptop } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { localStudioPath } from "../model/paths";

export type LocalStudioLinkProps = {
  /** Проект, который предложить открыть в локальной Студии. */
  projectId?: string | null;
  /** button: кнопка `btn`; link: ссылка в тексте. */
  variant?: "button" | "link";
  /** Своя подпись вместо «Локальная версия». */
  children?: ReactNode;
  className?: string;
};

/**
 * Ссылка на экран «Локальная версия» облачной Студии. Её ставят подсказки
 * «соберите локально», пустые состояния, онбординг и справка.
 */
export const LocalStudioLink = ({
  projectId = null,
  variant = "link",
  children,
  className,
}: LocalStudioLinkProps) => {
  const { t } = useTranslation("localStudio");
  return (
    <Link
      to={localStudioPath(projectId)}
      className={clsx(variant === "button" && "btn", className)}
      style={variant === "button" ? { textDecoration: "none" } : undefined}
      data-testid="local-studio-link"
    >
      {variant === "button" && <Laptop size={13} aria-hidden="true" />}
      {children ?? t("link.label")}
    </Link>
  );
};
