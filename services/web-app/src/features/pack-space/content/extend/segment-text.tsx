import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import type { DocumentSegmentProps } from "../contract";
import { fileLabel, resolveDocumentFile, textFilesOf } from "../documents";
import { TextEditor } from "../text/TextEditor";
import { useContentNav } from "../useContentNav";
import { useSpaceNav } from "../../context/useSpaceNav";

// S8b: сегмент «Текст» экрана документа (docs/design/pack-studio-ux.md, 5.5 и 12.7). Текст
// сохраняется сам (`text/useAutosaveFile`), кнопок «Сохранить» и «Отменить правки» нет.
const TextSegment = ({
  workspaceId,
  versionDir,
  doc,
  file,
  readOnly,
}: DocumentSegmentProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const nav = useContentNav();
  const space = useSpaceNav();
  const files = textFilesOf(doc);
  const current = resolveDocumentFile(doc, file, i18n.language, versionDir);
  if (!current) {
    return <p className="sp-ct-empty">{t("text.empty")}</p>;
  }
  return (
    <div className="sp-ct-text">
      {files.length > 1 && (
        <nav className="sp-ct-files" aria-label={t("text.files")}>
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
      <TextEditor
        workspaceId={workspaceId}
        path={current.path}
        readOnly={readOnly}
        onCopy={() => {
          // Кнопку «Править копию» делает S4; параметр `copy` зарезервирован за ним (12.6).
          space.go({ extra: { copy: "1" } });
        }}
      />
    </div>
  );
};

export default TextSegment;
