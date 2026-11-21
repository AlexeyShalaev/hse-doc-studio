import { RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  packFormKind,
  usePackVersionModel,
  versionRefOf,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { Button, ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { VersionSection } from "../lib/focus";
import { ModelEditorProvider, useModelEditor } from "../model/modelEditor";
import { ChecksFileSection } from "./checks/ChecksSections";
import { DocForm } from "./documents/DocForm";
import { VersionForm } from "./VersionForm";
import "./packForms.css";

export type PackFormPaneProps = {
  workspaceId: string;
  path: string;
  /** Форма записала файлы: проверки, класс версии, git (как после сохранения в редакторе). */
  onSaved: (changed: string[]) => void;
  /** Открыть файл в редакторе (форма документа из ростера версии). */
  onOpenFile?: ((path: string) => void) | undefined;
  /** Переход к правилу: указатель JSON записи манифеста, которую форма выделяет. */
  at?: string | null | undefined;
  /**
   * Показать только один раздел формы версии, без полосы вкладок и без плашки «версия выпущена»:
   * «Содержимое» (pack-space) выбирает раздел навигацией и само говорит про выпущенную версию.
   */
  section?: VersionSection | undefined;
};

/** Причина отказа сервера под текстом ошибки (`model_invalid`, `yaml_patch_conflict`). */
const reasonOf = (error: unknown): string | null => {
  if (!(error instanceof ApiError)) return null;
  const reason = error.data?.reason;
  return typeof reason === "string" ? reason : null;
};

const Status = ({ quietReadOnly }: { quietReadOnly: boolean }) => {
  const { t } = useTranslation("packForms");
  const { busy, error, stale, readOnly, clearError, model } = useModelEditor();
  const reason = reasonOf(error);
  return (
    <div className="pf-status" aria-live="polite">
      {readOnly && !quietReadOnly && (
        <Notice tone="info" role="status" text={t("readOnly")} />
      )}
      {stale ? (
        <Notice
          tone="warn"
          role="alert"
          text={t("stale")}
          action={
            <Button size="xs" variant="ghost" onClick={clearError}>
              {t("dismiss")}
            </Button>
          }
        />
      ) : error ? (
        <Notice
          tone="err"
          role="alert"
          text={
            <>
              {packErrorText(error)}
              {reason && <span className="pf-reason mono">{reason}</span>}
            </>
          }
          action={
            <Button size="xs" variant="ghost" onClick={clearError}>
              <RotateCcw size="0.6875rem" />
              {t("dismiss")}
            </Button>
          }
        />
      ) : null}
      {model.problems.length > 0 && !readOnly && (
        <p className="pf-hint" data-testid="pf-problems-note">
          {t("problemsNote", { count: model.problems.length })}
        </p>
      )}
      {busy && (
        <span className="pf-saving">
          <Spinner size="sm" />
          {t("saving")}
        </span>
      )}
    </div>
  );
};

/**
 * Вкладка «Форма» у манифеста (template-studio.md, 5.0): правка структуры пака
 * мышкой. Запись идёт точечными правками YAML тем же путём, что ручная правка;
 * «Исходник» рядом показывает тот же файл.
 */
export const PackFormPane = ({
  workspaceId,
  path,
  onSaved,
  onOpenFile,
  at,
  section,
}: PackFormPaneProps) => {
  const { t } = useTranslation("packForms");
  const ref = versionRefOf(path);
  const kind = packFormKind(path);
  const query = usePackVersionModel(workspaceId, ref);
  if (ref === null || kind === null) return null;
  if (query.isPending) {
    return (
      <div className="pf-loading">
        <Spinner size="md" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <ErrorState
        title={t("unreadable")}
        description={packErrorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <ModelEditorProvider
      workspaceId={workspaceId}
      versionRef={ref}
      model={query.data}
      onSaved={onSaved}
    >
      <div className="pf-pane" data-testid="pack-form-pane">
        <Status quietReadOnly={section !== undefined} />
        {kind === "checks" ? (
          <ChecksFileSection
            workspaceId={workspaceId}
            path={path}
            onSaved={onSaved}
          />
        ) : kind === "doc" ? (
          <DocForm docId={path.split("/").slice(-2)[0] ?? ""} at={at} />
        ) : (
          <VersionForm
            workspaceId={workspaceId}
            path={path}
            onSaved={onSaved}
            onOpenFile={onOpenFile}
            at={at}
            section={section}
          />
        )}
      </div>
    </ModelEditorProvider>
  );
};
