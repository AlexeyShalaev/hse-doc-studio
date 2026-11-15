import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, FolderUp, Upload } from "lucide-react";
import { FileTree } from "@widgets/FileTree";
import type { FileNode, FileTreeUpload } from "@widgets/FileTree";
import {
  FileUploadDialog,
  useProjectFileUpload,
} from "@features/project-file-upload";

export type FilesPanelProps = {
  projectId: string;
};

/**
 * Оболочка режима «Файлы»: скелет панели + дерево внутри.
 *
 * Живёт в слое pages, а не в widgets, сознательно: обёртка обязана
 * импортировать виджет FileTree, а виджету импортировать другой виджет
 * запрещено. Страница — тот слой, которому композиция виджетов разрешена.
 *
 * Кнопка показа служебных файлов переехала сюда из внутренней шапки FileTree,
 * которую сняли вместе с собственной рамкой дерева.
 */
export const FilesPanel = ({ projectId }: FilesPanelProps) => {
  const { t } = useTranslation("workbench");
  const { t: tChrome } = useTranslation("appChrome");
  const { t: tUpload } = useTranslation("fileUpload");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isShowingHidden, setIsShowingHidden] = useState(false);

  const selectedPath = searchParams.get("file") ?? undefined;
  // Загрузка с компьютера живёт здесь: кнопки шапки и дерево (меню, перетаскивание) делят одну.
  const upload = useProjectFileUpload(projectId);
  const { canUpload, pick, dropFiles } = upload;
  const treeUpload: FileTreeUpload = useMemo(
    () => ({ enabled: canUpload, pick, drop: dropFiles }),
    [canUpload, pick, dropFiles],
  );

  // Выбор файла — это адрес, а не состояние компонента: по ?file=<путь>&line=<n>
  // в дерево ссылаются находки проверок, и эта ссылка обязана продолжать
  // работать. Строку запроса пересобираем от текущей, чтобы не потерять line.
  const handleSelect = (node: FileNode): void => {
    if (node.type === "folder") return;
    const next = new URLSearchParams(searchParams);
    next.set("file", node.path);
    next.delete("line");
    void navigate(`/projects/${projectId}/files?${next.toString()}`);
  };

  return (
    <div className="workbench-panel">
      <div className="panel-head">
        <span className="panel-head-title">{t("files.title")}</span>
        <div className="panel-head-actions">
          {canUpload && (
            <>
              <button
                type="button"
                className="icon-btn sm tt"
                data-tt={tUpload("actions.uploadFiles")}
                aria-label={tUpload("actions.uploadFiles")}
                onClick={() => {
                  pick("", "files");
                }}
              >
                <Upload size="0.75rem" />
              </button>
              <button
                type="button"
                className="icon-btn sm tt"
                data-tt={tUpload("actions.uploadFolder")}
                aria-label={tUpload("actions.uploadFolder")}
                onClick={() => {
                  pick("", "folder");
                }}
              >
                <FolderUp size="0.75rem" />
              </button>
            </>
          )}
          <button
            type="button"
            className="icon-btn sm tt"
            data-tt={
              isShowingHidden
                ? tChrome("fileTree.hideHidden")
                : tChrome("fileTree.showHidden")
            }
            aria-pressed={isShowingHidden}
            onClick={() => {
              setIsShowingHidden((shown) => !shown);
            }}
          >
            {isShowingHidden ? (
              <EyeOff size="0.75rem" />
            ) : (
              <Eye size="0.75rem" />
            )}
          </button>
        </div>
      </div>
      <div
        className="panel-body"
        style={{ padding: "0.25rem 0.125rem 0.625rem" }}
      >
        <FileTree
          projectId={projectId}
          selectedPath={selectedPath}
          onSelect={handleSelect}
          showHidden={isShowingHidden}
          upload={treeUpload}
        />
      </div>
      <FileUploadDialog upload={upload} />
    </div>
  );
};
