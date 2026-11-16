import { useTranslation } from "react-i18next";
import { packErrorText } from "../lib/errorText";
import { gitFailureHint } from "../lib/gitErrors";

/**
 * Текст отказа Студии шаблонов для баннера. У `workspace_git_failed` под текстом
 * свёрнутая подсказка сервера (подкоманда git и строка ошибки без адресов и
 * путей): её человек пересылает вместе со скриншотом, журнала сервера не нужно.
 */
export const PackErrorText = ({ error }: { error: unknown }) => {
  const { t } = useTranslation("errors");
  const hint = gitFailureHint(error);
  const text = packErrorText(error);
  if (hint === null) return <>{text}</>;
  return (
    <>
      {text}
      <details className="ps-error-hint" data-testid="git-failure-hint">
        <summary>{t("message.gitHint")}</summary>
        <code>{hint}</code>
      </details>
    </>
  );
};
