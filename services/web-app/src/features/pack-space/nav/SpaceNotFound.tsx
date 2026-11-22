import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { PACK_STUDIO_PATH } from "@entities/pack-studio";
import { EmptyState } from "@shared/ui";

/**
 * Адрес ведёт на пространство, которого нет (удалили, ссылка неточная): причина и один следующий
 * шаг, ссылка в список (pack-studio-ux.md, 5.10). Вместо сырой ошибки запроса.
 */
export const SpaceNotFound = () => {
  const { t } = useTranslation("packSpace");
  return (
    <EmptyState
      framed
      title={t("shell.notFound.title")}
      description={t("shell.notFound.lead")}
      action={
        <Link className="btn primary" to={PACK_STUDIO_PATH}>
          {t("shell.notFound.action")}
        </Link>
      }
      testId="space-not-found"
    />
  );
};
