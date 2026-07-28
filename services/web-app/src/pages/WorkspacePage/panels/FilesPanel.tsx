import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff } from "lucide-react";
import { FileTree } from "@widgets/FileTree";
import type { FileNode } from "@widgets/FileTree";

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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isShowingHidden, setIsShowingHidden] = useState(false);

  const selectedPath = searchParams.get("file") ?? undefined;

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
            {isShowingHidden ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
        </div>
      </div>
      <div className="panel-body" style={{ padding: "4px 2px 10px" }}>
        <FileTree
          projectId={projectId}
          selectedPath={selectedPath}
          onSelect={handleSelect}
          showHidden={isShowingHidden}
        />
      </div>
    </div>
  );
};
