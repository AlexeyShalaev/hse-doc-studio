import { useTranslation } from "react-i18next";
import { PackTreePanel } from "@features/pack-tree";
import type { ContentPartProps } from "../contract";
import { LegacyFileEditor } from "../legacy/LegacyFileEditor";
import { useContentNav } from "../useContentNav";

// S8d: ЗАМЕНИТЬ ЭТОТ ФАЙЛ. «Все файлы» пока прежнее дерево и прежний редактор; «Новый пак»,
// «Новый шаблон» и мастер новой версии из дерева S8d подключает по месту
// (docs/design/pack-studio-ux.md, 7.4 и 12.7).
const FilesPart = ({ workspaceId, file, at }: ContentPartProps) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  return (
    <div className="sp-ct-files-part">
      <div className="sp-ct-tree" aria-label={t("content.legacy.treeTitle")}>
        <PackTreePanel
          workspaceId={workspaceId}
          selectedPath={file}
          onSelect={(path) => {
            nav.toPart("files", { file: path });
          }}
        />
      </div>
      <div className="sp-ct-tree-main">
        {file ? (
          <LegacyFileEditor
            workspaceId={workspaceId}
            path={file}
            owner="part-files"
            at={at}
            onOpenFile={nav.toFile}
          />
        ) : (
          <div className="sp-ct-stub">
            <h2>{t("content.legacy.pickTitle")}</h2>
            <p>{t("content.legacy.pickLead")}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default FilesPart;
