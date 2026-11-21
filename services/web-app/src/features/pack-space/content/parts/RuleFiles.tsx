import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { usePackTree } from "@entities/pack-studio";
import { useContentNav } from "../useContentNav";

// Файлы правил версии (`checks/*.yaml`): у каждого своя форма, а в навигации «Содержимого» им
// иначе нет места. Ссылка открывает файл в «Все файлы» сразу на форме.
export const RuleFiles = ({
  workspaceId,
  versionDir,
}: {
  workspaceId: string;
  versionDir: string;
}) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  const tree = usePackTree(workspaceId);
  const prefix = `${versionDir}/checks/`;
  const files = (tree.data?.files ?? []).filter(
    (file) =>
      !file.is_dir &&
      file.path.startsWith(prefix) &&
      /^[^/]+\.yaml$/.test(file.path.slice(prefix.length)),
  );
  if (files.length === 0) return null;
  return (
    <section className="sp-ct-part-rules" data-testid="ct-rule-files">
      <h2 className="sp-ct-part-h2">{t("content.parts.rules.files")}</h2>
      <p className="sp-ct-part-note">{t("content.parts.rules.filesLead")}</p>
      <ul className="sp-ct-part-list">
        {files.map((file) => {
          const name = file.path.slice(prefix.length);
          return (
            <li key={file.path}>
              <Link
                replace
                to={nav.partHref("files", { file: file.path })}
                className="sp-ct-part-link"
                onClick={nav.guardClick}
                data-testid={`ct-rule-file-${name}`}
              >
                <span className="mono">{name}</span>
                <span className="sp-ct-part-open">
                  {t("content.parts.rules.open")}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
};
