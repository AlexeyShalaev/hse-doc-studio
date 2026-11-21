import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PackVersionRef } from "@entities/pack-studio";
import { PackTreePanel } from "@features/pack-tree";
import type { NewPackTarget } from "@features/pack-scaffold";
import { CreateDialog } from "../../nav/CreateDialog";
import { useSpaceNav } from "../../context/useSpaceNav";
import { useSpacePhone } from "../../shell/phoneContext";
import type { ContentPartProps } from "../contract";
import { useContentNav } from "../useContentNav";
import { FileView } from "./FileView";
import "./space-content-parts.css";

// «Все файлы» (pack-studio-ux.md, 5.5, срез S8d): прежнее дерево для опытных и редактор файла с
// автосохранением. «Новый пак» и «Новый шаблон» создаются тут же, по месту; «Править копию»
// заменяет «Новую версию» значка дерева (главная кнопка пространства, S4).
const FilesPart = ({
  workspaceId,
  versionDir,
  file,
  at,
  readOnly,
}: ContentPartProps) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  const space = useSpaceNav();
  const [create, setCreate] = useState<NewPackTarget | null>(null);
  // Телефон: дерево и файл две страницы, а не две колонки. Без файла дерево, с файлом файл
  // и «назад» к дереву (его рисует `ContentMain`).
  const phone = useSpacePhone();
  const showTree = !phone || !file;
  const showFile = !phone || Boolean(file);
  // Замок версии, которая открыта в Студии: чужую выпущенную версию закрывает сервер.
  const locked = readOnly && (file?.startsWith(`${versionDir}/`) ?? false);
  const open = (ref: PackVersionRef) => {
    space.go({ ref });
  };
  return (
    <div className="sp-ct-part" data-testid="ct-files">
      {showTree && (
        <div className="sp-ct-part-lead">
          <p>{t("content.parts.files.lead")}</p>
        </div>
      )}
      <div className="sp-ct-files-part">
        {showTree && (
        <div
          className="sp-ct-tree"
          aria-label={t("content.parts.files.treeTitle")}
        >
          <PackTreePanel
            workspaceId={workspaceId}
            selectedPath={file}
            onSelect={(path) => {
              nav.toPart("files", { file: path });
            }}
            onNewPack={() => {
              setCreate({ kind: "pack" });
            }}
            onNewTemplate={(pack) => {
              setCreate({ kind: "template", pack });
            }}
          />
        </div>
        )}
        {showFile && (
        <div className="sp-ct-tree-main">
          {file ? (
            <FileView
              key={file}
              workspaceId={workspaceId}
              path={file}
              at={at}
              readOnly={locked}
              onCopy={() => {
                space.go({ extra: { copy: "1" } });
              }}
              onOpenFile={nav.toFile}
            />
          ) : (
            <div className="sp-ct-stub">
              <h2>{t("content.parts.files.pickTitle")}</h2>
              <p>{t("content.parts.files.pickLead")}</p>
            </div>
          )}
        </div>
        )}
      </div>
      <CreateDialog
        workspaceId={workspaceId}
        target={create}
        onClose={() => {
          setCreate(null);
        }}
        onOpen={open}
      />
    </div>
  );
};

export default FilesPart;
