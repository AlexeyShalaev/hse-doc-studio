import { CircleHelp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { useHelpStore } from "../model/helpStore";

export type HelpAnchorProps = {
  /** Ключ статьи: путь файла в services/user-docs без языка, например `runbooks/git-sync`. */
  article: string;
  /** Шаг (с единицы), к которому панель прокрутит и который подсветит. */
  step?: number;
  className?: string;
};

/**
 * Значок «?» у одного сложного поля, а не у экрана: открывает ту же панель справки сразу на
 * шаге, который это поле объясняет.
 */
export const HelpAnchor = ({ article, step, className }: HelpAnchorProps) => {
  const { t } = useTranslation("help");
  const open = useHelpStore((s) => s.open);
  return (
    <button
      type="button"
      className={clsx("help-anchor tt", className)}
      data-tt={t("anchor")}
      aria-label={t("anchor")}
      data-help-article={article}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        open(article, step);
      }}
    >
      <CircleHelp size="0.8125rem" aria-hidden="true" />
    </button>
  );
};
