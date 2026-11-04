import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { ShieldCheck, CaseSensitive } from "lucide-react";
import type { ConflictFile, FileResolution } from "@entities/git-sync";
import { WholeFileChoice } from "./WholeFileChoice";

export type GroupChoiceResolverProps = {
  file: ConflictFile;
  resolution: FileResolution | null | undefined;
  theirsAuthor: string | null;
  onChoose: (choice: string) => void;
};

/**
 * Конфликты, которые решаются целым набором: подписи документа (их нельзя
 * смешивать) и имена, различающиеся только регистром. Сверху объяснение, почему
 * так, ниже обычный выбор версии.
 */
export const GroupChoiceResolver = ({
  file,
  resolution,
  theirsAuthor,
  onChoose,
}: GroupChoiceResolverProps) => {
  const { t } = useTranslation("gitConflicts");
  const type =
    file.conflict_type === "case_collision"
      ? "case_collision"
      : "signature_group";
  const Icon = type === "signature_group" ? ShieldCheck : CaseSensitive;
  return (
    <div className="flex flex-col" style={{ gap: "0.625rem" }}>
      <Notice
        tone="warn"
        role="status"
        text={
          <span className="flex flex-col" style={{ gap: "0.125rem" }}>
            <strong className="flex items-center" style={{ gap: "0.375rem" }}>
              <Icon size="0.8125rem" aria-hidden="true" />
              {t(`group.${type}.title`)}
            </strong>
            <span>{t(`group.${type}.text`)}</span>
            {type === "signature_group" && file.doc_id && (
              <span className="dim">
                {t("group.signature_group.doc", { doc: file.doc_id })}
              </span>
            )}
          </span>
        }
      />
      <WholeFileChoice
        file={file}
        resolution={resolution}
        theirsAuthor={theirsAuthor}
        onChoose={onChoose}
      />
    </div>
  );
};
