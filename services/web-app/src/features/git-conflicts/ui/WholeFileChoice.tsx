import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { ConflictFile, FileResolution } from "@entities/git-sync";
import { SideFacts } from "./SideFacts";

export type WholeFileChoiceProps = {
  file: ConflictFile;
  resolution: FileResolution | null | undefined;
  theirsAuthor: string | null;
  onChoose: (choice: string) => void;
};

const ORDER = ["mine", "theirs", "newest"] as const;

// Подписи вариантов зависят от того, что случилось с файлом.
const labelKey = (file: ConflictFile, choice: string): string => {
  if (
    file.conflict_type === "deleted_by_them" ||
    file.conflict_type === "deleted_by_us" ||
    file.conflict_type === "signature_group" ||
    file.conflict_type === "case_collision"
  ) {
    return `file.${file.conflict_type}.${choice}`;
  }
  return `file.choice.${choice}`;
};

/**
 * Выбор версии файла целиком: для файлов, которые не разобрать по частям
 * (картинки, поля формы, удаление против правки).
 */
export const WholeFileChoice = ({
  file,
  resolution,
  theirsAuthor,
  onChoose,
}: WholeFileChoiceProps) => {
  const { t } = useTranslation("gitConflicts");
  const groupId = useId();
  const current = resolution?.kind === "file" ? resolution.choice : null;
  const options = ORDER.filter((choice) => file.allowed.includes(choice));

  const factsFor = (choice: string): React.ReactNode => {
    if (choice === "mine") return <SideFacts side={file.sides.ours} />;
    if (choice === "theirs") return <SideFacts side={file.sides.theirs} />;
    // «Более новая»: смотрим, чья сторона свежее.
    const ours = Date.parse(file.sides.ours.at ?? "") || 0;
    const theirs = Date.parse(file.sides.theirs.at ?? "") || 0;
    return (
      <span className="dim">
        {t("file.newestHint", {
          author:
            (theirs > ours ? theirsAuthor : file.sides.ours.author) ??
            t("side.unknown"),
        })}
      </span>
    );
  };

  return (
    <div
      role="radiogroup"
      aria-label={t("file.groupLabel")}
      className="flex flex-col"
      style={{ gap: 8 }}
    >
      {options.map((choice) => {
        const id = `${groupId}-${choice}`;
        const checked = current === choice;
        return (
          <label
            key={choice}
            htmlFor={id}
            className="card whole-choice"
            data-checked={checked ? "true" : undefined}
          >
            <input
              id={id}
              type="radio"
              name={groupId}
              checked={checked}
              onChange={() => {
                onChoose(choice);
              }}
            />
            <span className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {t(labelKey(file, choice))}
                {file.default_resolution === choice && (
                  <span
                    className="chip accent"
                    style={{ marginLeft: 8, fontFamily: "var(--font-sans)" }}
                  >
                    {t("file.recommended")}
                  </span>
                )}
              </span>
              <span style={{ fontSize: 11.5 }}>{factsFor(choice)}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
};
