import { useSearchParams } from "react-router";
import { useCapabilities } from "@entities/session";
import { OutcomeEntry } from "./OutcomeRoute";
import { WorkspaceScreen } from "./WorkspaceScreen";

/**
 * Вход в пространство (`/pack-studio/w/<id>`). Режим «Файлы» (дерево, редактор, предпросмотр)
 * открывается, когда в адресе есть файл (`?file=`) или `?view=files`. Без них по умолчанию
 * экран «Результат», но только если сервер его поддерживает (`capabilities.pack_outcome`):
 * без этого признака открывается прежний экран «Файлы». Ссылки на файлы и закладки на режим
 * «Файлы» работают как раньше.
 */
export const WorkspaceEntry = () => {
  const [params] = useSearchParams();
  const { has } = useCapabilities();
  const files =
    params.has("file") ||
    params.get("view") === "files" ||
    !has("pack_outcome");
  return files ? <WorkspaceScreen /> : <OutcomeEntry />;
};
