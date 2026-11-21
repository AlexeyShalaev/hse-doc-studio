import { lazy, Suspense, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { notifyPackFilesSaved, packStudioKeys } from "@entities/pack-studio";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { Spinner } from "@shared/ui";
import type { VersionSection } from "@features/pack-forms";

// Формы манифестов `pack-forms` (версия, документ, файл правил) в новой навигации: «Условия»
// документа, разделы версии и форма файла в «Все файлы». Свой чанк, как в прежнем экране: форма и
// её словарь грузятся с первым открытием. `section` показывает один раздел формы версии без
// полосы вкладок: раздел выбирает левая навигация «Содержимого».
const PackFormPane = lazy(() =>
  Promise.all([import("@features/pack-forms"), loadPackFormsNamespace()]).then(
    ([m]) => ({ default: m.PackFormPane }),
  ),
);

export type FormPaneProps = {
  workspaceId: string;
  /** Манифест, форма которого нужна: `version.yaml`, `doc.yaml` или файл правил. */
  path: string;
  at?: string | null;
  /** Раздел формы версии (только для `version.yaml`). */
  section?: VersionSection | undefined;
  onOpenFile?: ((path: string) => void) | undefined;
};

export const FormPane = ({
  workspaceId,
  path,
  at,
  section,
  onOpenFile,
}: FormPaneProps) => {
  const client = useQueryClient();
  // Форма записала файлы версии: как сохранение в редакторе, плюс места подписей и git.
  const onSaved = useCallback(() => {
    notifyPackFilesSaved(workspaceId);
    void client.invalidateQueries({
      queryKey: packStudioKeys.git(workspaceId),
    });
    void client.invalidateQueries({
      queryKey: packStudioKeys.signaturesAll(workspaceId),
    });
  }, [client, workspaceId]);
  return (
    <div className="sp-ct-legacy" data-testid="ct-legacy-form">
      <Suspense
        fallback={
          <div className="flex justify-center" style={{ padding: "2rem" }}>
            <Spinner size="md" />
          </div>
        }
      >
        <PackFormPane
          workspaceId={workspaceId}
          path={path}
          onSaved={onSaved}
          at={at ?? null}
          section={section}
          onOpenFile={onOpenFile}
        />
      </Suspense>
    </div>
  );
};
