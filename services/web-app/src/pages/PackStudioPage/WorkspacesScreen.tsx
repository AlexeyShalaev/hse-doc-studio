import { useNavigate } from "react-router";
import { packWorkspacePath } from "@entities/pack-studio";
import { useCapabilities } from "@entities/session";
import { FolderPickerModal } from "@features/folder-picker";
import {
  WorkspacesView,
  readLastOpened,
  writeLastOpened,
} from "@features/pack-workspaces";

/** Начало Студии шаблонов: список пространств и подключение нового (pack-studio-ux.md, 5.1). */
export const WorkspacesScreen = () => {
  const navigate = useNavigate();
  const { has } = useCapabilities();
  // Папка на диске есть только там, где Студия видит файловую систему (локально).
  const allowFolder = has("fs_browse");
  return (
    <WorkspacesView
      allowFolder={allowFolder}
      renderFolderPicker={
        allowFolder ? (props) => <FolderPickerModal {...props} /> : undefined
      }
      lastOpenedId={readLastOpened()}
      onOpen={(id) => {
        writeLastOpened(id);
        void navigate(packWorkspacePath(id));
      }}
    />
  );
};
