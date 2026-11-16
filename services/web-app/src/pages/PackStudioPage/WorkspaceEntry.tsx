import { useSearchParams } from "react-router";
import { OutcomeEntry } from "./OutcomeRoute";
import { WorkspaceScreen } from "./WorkspaceScreen";

/**
 * Вход в пространство (`/pack-studio/w/<id>`). Режим «Файлы» (дерево, редактор, предпросмотр)
 * открывается, когда в адресе есть файл (`?file=`) или `?view=files`. Без них по умолчанию
 * экран «Результат»: ссылки на файлы и закладки на режим «Файлы» работают как раньше.
 */
export const WorkspaceEntry = () => {
  const [params] = useSearchParams();
  const files = params.has("file") || params.get("view") === "files";
  return files ? <WorkspaceScreen /> : <OutcomeEntry />;
};
