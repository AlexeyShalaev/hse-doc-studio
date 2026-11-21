import { lazy, Suspense, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { notifyPackFilesSaved, packStudioKeys } from "@entities/pack-studio";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { Spinner } from "@shared/ui";

// ВРЕМЕННО (S8a): формы манифестов прежнего интерфейса, подключённые к новой навигации. S8d
// заменяет их разделами на тех же формах `pack-forms`, S8a держит ими «Условия» документа и
// разделы версии, чтобы ни одна функция не пропала раньше времени (карта паритета, 7.4).
// Свой чанк, как в прежнем экране: форма и её словарь грузятся с первым открытием.
const PackFormPane = lazy(() =>
  Promise.all([import("@features/pack-forms"), loadPackFormsNamespace()]).then(
    ([m]) => ({ default: m.PackFormPane }),
  ),
);

export type LegacyFormPaneProps = {
  workspaceId: string;
  /** Манифест, форма которого нужна: `version.yaml`, `doc.yaml` или файл правил. */
  path: string;
  at?: string | null;
  onOpenFile?: ((path: string) => void) | undefined;
};

export const LegacyFormPane = ({
  workspaceId,
  path,
  at,
  onOpenFile,
}: LegacyFormPaneProps) => {
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
          onOpenFile={onOpenFile}
        />
      </Suspense>
    </div>
  );
};
