import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useConflictDiff, type ConflictDiffView } from "@entities/git-sync";
import { Spinner } from "@shared/ui/Spinner";
import { Notice } from "@shared/ui/ConflictKit";
import { DiffPatch, countChanges } from "@shared/ui/DiffPatch";

export type ConflictFileDiffProps = {
  projectId: string;
  path: string;
  view: ConflictDiffView;
  /** Отметка сохранённого выбора: итог зависит от него. */
  revision: number;
  /** Выбор ещё не дошёл до сервера: итог пока считать рано. */
  isSaving: boolean;
  maxHeight?: number;
};

/**
 * Дифф одного файла в той же вёрстке, что «Версии» и обновление шаблона:
 * мои правки, чужие правки или итог слияния с учётом сделанного выбора.
 */
export const ConflictFileDiff = ({
  projectId,
  path,
  view,
  revision,
  isSaving,
  maxHeight = 520,
}: ConflictFileDiffProps) => {
  const { t } = useTranslation("gitConflicts");
  const waitsForSave = view === "result" && isSaving;
  const { data, isLoading, isError, refetch } = useConflictDiff(
    projectId,
    waitsForSave ? null : path,
    view,
    view === "result" ? String(revision) : null,
  );
  const stat = useMemo(
    () =>
      data && !data.binary ? countChanges(data.patch) : { add: 0, del: 0 },
    [data],
  );

  const body = ((): React.ReactNode => {
    if (waitsForSave || isLoading) {
      return (
        <div
          className="flex items-center justify-center"
          style={{ gap: 8, padding: 24 }}
        >
          <Spinner size="sm" />
          <span className="dim" style={{ fontSize: 12 }}>
            {waitsForSave ? t("diff.saving") : t("diff.loading")}
          </span>
        </div>
      );
    }
    if (isError || !data) {
      return (
        <Notice
          tone="err"
          role="alert"
          text={t("diff.error")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                void refetch();
              }}
            >
              {t("diff.retry")}
            </button>
          }
        />
      );
    }
    if (data.binary) {
      return (
        <div className="card dim" style={{ padding: 14, fontSize: 12 }}>
          {t("diff.binary")}
        </div>
      );
    }
    if (data.patch.trim() === "") {
      return (
        <div className="card dim" style={{ padding: 14, fontSize: 12 }}>
          {t("diff.empty")}
        </div>
      );
    }
    return (
      <>
        {data.truncated && (
          <Notice tone="warn" role="status" text={t("diff.truncated")} />
        )}
        <DiffPatch
          file={{
            path: data.path,
            change: "M",
            patch: data.patch,
            binary: false,
          }}
          stat={stat}
          maxHeight={maxHeight}
        />
      </>
    );
  })();

  return (
    <div className="flex flex-col" style={{ gap: 8, minWidth: 0 }}>
      <p className="dim" style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
        {t(`diff.hint.${view}`)}
      </p>
      {body}
    </div>
  );
};
