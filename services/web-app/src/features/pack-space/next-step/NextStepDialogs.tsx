import { RepoAccessDialog, StartOverDialog } from "@features/pack-git";
import {
  notifyPackFilesSaved,
  type PackGit,
  type PackWorkspace,
} from "@entities/pack-studio";

/**
 * Окна главной кнопки: доступ к репозиторию («Проверить доступ») и сброс на свежую основную
 * ветку («Начать новую правку»). Отдельным чанком: тянут прежние диалоги git, а открываются
 * редко.
 */
const NextStepDialogs = ({
  dialog,
  workspace,
  git,
  onClose,
}: {
  dialog: "access" | "startOver";
  workspace: PackWorkspace;
  git: PackGit | null;
  onClose: () => void;
}) =>
  dialog === "access" ? (
    <RepoAccessDialog workspace={workspace} isOpen onClose={onClose} />
  ) : git ? (
    <StartOverDialog
      git={git}
      isOpen
      onClose={onClose}
      onDone={() => {
        notifyPackFilesSaved(workspace.id);
      }}
    />
  ) : null;

export default NextStepDialogs;
