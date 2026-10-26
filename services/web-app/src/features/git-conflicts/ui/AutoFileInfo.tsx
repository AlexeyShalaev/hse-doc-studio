import { useTranslation } from "react-i18next";
import type { ConflictFile } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";

export type AutoFileInfoProps = {
  file: ConflictFile;
  theirsAuthor: string | null;
};

/** Что сервер сделал с файлом сам. Решать тут нечего, но знать полезно. */
export const AutoFileInfo = ({ file, theirsAuthor }: AutoFileInfoProps) => {
  const { t } = useTranslation("gitConflicts");
  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <Notice
        tone="info"
        role="status"
        text={t(`auto.info.${file.action}`, {
          defaultValue: t("auto.info.fallback"),
          author: theirsAuthor ?? t("side.unknown"),
        })}
      />
      {file.copy_path && (
        <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
          {t("auto.copy")}{" "}
          <span className="mono" style={{ fontSize: 11.5 }}>
            {file.copy_path}
          </span>
        </p>
      )}
    </div>
  );
};
