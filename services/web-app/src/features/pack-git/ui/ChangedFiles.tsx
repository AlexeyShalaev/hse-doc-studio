import { useTranslation } from "react-i18next";
import type { PackFileChange } from "@entities/pack-studio";

const LETTER: Record<PackFileChange["status"], string> = {
  added: "A",
  modified: "M",
  deleted: "D",
};

/** Список изменённых файлов: буква изменения и путь от папки паков. */
export const ChangedFiles = ({
  files,
  onOpen,
  testId,
}: {
  files: readonly PackFileChange[];
  /** Открыть файл в редакторе (удалённый не открывается). */
  onOpen?: ((path: string) => void) | undefined;
  testId?: string;
}) => {
  const { t } = useTranslation("packStudio");
  return (
    <ul className="ps-git-files" data-testid={testId}>
      {files.map((file) => {
        const body = (
          <>
            <span
              className={`ps-git-letter ps-git-letter-${file.status}`}
              title={t(`git.status.${file.status}`)}
            >
              {LETTER[file.status]}
            </span>
            <span className="mono ps-git-path">{file.path}</span>
          </>
        );
        return (
          <li key={file.path}>
            {onOpen && file.status !== "deleted" ? (
              <button
                type="button"
                className="ps-git-file"
                onClick={() => {
                  onOpen(file.path);
                }}
              >
                {body}
              </button>
            ) : (
              <span className="ps-git-file">{body}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
};
