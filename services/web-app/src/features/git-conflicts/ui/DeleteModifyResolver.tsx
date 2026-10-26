import { useId } from "react";
import { useTranslation } from "react-i18next";
import { FileCheck, Trash2 } from "lucide-react";
import type { ConflictFile, FileResolution } from "@entities/git-sync";
import { formatWhen } from "../lib/format";
import { SideFacts } from "./SideFacts";

export type DeleteModifyResolverProps = {
  file: ConflictFile;
  resolution: FileResolution | null | undefined;
  theirsAuthor: string | null;
  /** Кто удалил, если сервер сказал это отдельно от типа конфликта. */
  deletedBy?: "ours" | "theirs" | null;
  onChoose: (choice: string) => void;
};

/**
 * Один удалил файл, другой его изменил. Два варианта сформулированы как
 * последствия («файл останется», «файл исчезнет»), а под ними видно, кто и
 * когда менял, чтобы не гадать, что именно потеряется.
 */
export const DeleteModifyResolver = ({
  file,
  resolution,
  theirsAuthor,
  deletedBy = null,
  onChoose,
}: DeleteModifyResolverProps) => {
  const { t } = useTranslation("gitConflicts");
  const groupId = useId();
  const current = resolution?.kind === "file" ? resolution.choice : null;
  const byThem =
    file.conflict_type === "deleted_by_them" ||
    (file.conflict_type !== "deleted_by_us" && deletedBy === "theirs");
  const tone = byThem ? "them" : "us";
  // Сторона, которая файл изменила: её версия остаётся, если файл сохранить.
  const changed = byThem ? file.sides.ours : file.sides.theirs;
  const deleted = byThem ? file.sides.theirs : file.sides.ours;
  const changedBy = byThem ? file.sides.ours.author : theirsAuthor;
  const deletedAuthor = byThem
    ? (theirsAuthor ?? deleted.author)
    : deleted.author;
  const keepChoice = byThem ? "mine" : "theirs";
  const prefix = byThem ? "file.deleted_by_them" : "file.deleted_by_us";

  const options = (["mine", "theirs"] as const).filter(
    (choice) => file.allowed.length === 0 || file.allowed.includes(choice),
  );

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
        const keepsFile = choice === keepChoice;
        const Icon = keepsFile ? FileCheck : Trash2;
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
            <span className="flex flex-col" style={{ gap: 3, minWidth: 0 }}>
              <span
                className="flex items-center"
                style={{ gap: 6, fontSize: 13, fontWeight: 600 }}
              >
                <Icon
                  size={14}
                  aria-hidden="true"
                  style={{
                    flexShrink: 0,
                    color: keepsFile ? "var(--c-ok)" : "var(--c-err)",
                  }}
                />
                {t(`${prefix}.${choice}`)}
              </span>
              <span style={{ fontSize: 12, lineHeight: 1.5 }}>
                {t(`deleteModify.${tone}.${choice}`)}
              </span>
              <span className="dim" style={{ fontSize: 11.5 }}>
                {keepsFile ? (
                  <>
                    {t("deleteModify.changedBy", {
                      author: changedBy ?? t("side.unknown"),
                    })}
                    {" · "}
                    <SideFacts side={changed} />
                  </>
                ) : (
                  [
                    t("deleteModify.deletedBy", {
                      author: deletedAuthor ?? t("side.unknown"),
                    }),
                    formatWhen(deleted.at),
                  ]
                    .filter(Boolean)
                    .join(" · ")
                )}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
};
