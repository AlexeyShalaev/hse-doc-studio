import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { DocumentSegmentProps } from "../contract";
import { fileLabel, resolveDocumentFile, textFilesOf } from "../documents";
import { LegacyFileEditor } from "../legacy/LegacyFileEditor";
import { useContentNav } from "../useContentNav";

// S8b: ЗАМЕНИТЬ ЭТОТ ФАЙЛ. Здесь временно прежний редактор файла с кнопкой «Сохранить»;
// «Текст» с автосохранением (`useAutosaveFile`), «Вернуть как было» и плашкой ближайшего
// замечания пишет S8b, его файл целиком заменяет этот (docs/design/pack-studio-ux.md, 12.7).
const TextSegment = ({
  workspaceId,
  versionDir,
  doc,
  file,
}: DocumentSegmentProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const nav = useContentNav();
  const files = textFilesOf(doc);
  const current = resolveDocumentFile(doc, file, i18n.language, versionDir);
  if (!current) {
    return <p className="sp-ct-empty">{t("content.legacy.noText")}</p>;
  }
  return (
    <div className="sp-ct-text">
      {files.length > 1 && (
        <nav className="sp-ct-files" aria-label={t("content.legacy.file")}>
          {files.map((item) => (
            <Link
              key={item.path}
              replace
              to={nav.documentHref(doc.id, {
                segment: "text",
                file: item.path,
              })}
              className="sp-ct-chip"
              aria-current={item.path === current.path ? "page" : undefined}
              onClick={nav.guardClick}
            >
              {fileLabel(item)}
            </Link>
          ))}
        </nav>
      )}
      <LegacyFileEditor
        workspaceId={workspaceId}
        path={current.path}
        owner="segment-text"
        onOpenFile={nav.toFile}
      />
    </div>
  );
};

export default TextSegment;
