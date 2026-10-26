import { useTranslation } from "react-i18next";
import type { ConflictFileSide } from "@entities/git-sync";
import { formatFileSize } from "@shared/lib";
import { formatWhen } from "../lib/format";

/** Одна строка о стороне файла: автор, когда, размер; или «файла нет». */
export const SideFacts = ({ side }: { side: ConflictFileSide }) => {
  const { t } = useTranslation("gitConflicts");
  if (!side.exists) {
    return <span className="dim">{t("side.missing")}</span>;
  }
  const parts = [
    side.author,
    formatWhen(side.at),
    side.size != null ? formatFileSize(side.size) : null,
  ].filter((part): part is string => !!part);
  return <span className="dim">{parts.join(" · ") || t("side.exists")}</span>;
};
