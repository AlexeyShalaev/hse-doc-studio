import { lazy, Suspense, useCallback } from "react";
import { Spinner } from "@shared/ui";
import type { VersionSectionProps } from "../VersionForm";

// Формы проверок (срез T14): свой чанк, грузится с разделом или файлом правил.
const PackChecksConfigForm = lazy(() =>
  import("@features/pack-checks-form").then((m) => ({
    default: m.PackChecksConfigForm,
  })),
);
const PackChecksFileForm = lazy(() =>
  import("@features/pack-checks-form").then((m) => ({
    default: m.PackChecksFileForm,
  })),
);

const Loading = () => (
  <div className="pf-loading">
    <Spinner size="md" />
  </div>
);

const useSaved = (onSaved: (changed: string[]) => void) =>
  useCallback(
    (path: string) => {
      onSaved([path]);
    },
    [onSaved],
  );

/**
 * Раздел «Проверки» формы версии (5.7): `checks_version` (выключенные категории и правила,
 * переопределение важности). Правки идут маршрутом `.../checks/config` в той же очереди, что
 * правки модели, и обновляют модель.
 */
export const ChecksSection = ({
  workspaceId,
  path,
  onSaved,
}: VersionSectionProps) => {
  const saved = useSaved(onSaved);
  return (
    <Suspense fallback={<Loading />}>
      <PackChecksConfigForm
        workspaceId={workspaceId}
        path={path}
        onSaved={saved}
      />
    </Suspense>
  );
};

/** Форма файла правил `checks/*.yaml` (5.7): шапка, правила, «Проверить на предпросмотре». */
export const ChecksFileSection = ({
  workspaceId,
  path,
  onSaved,
}: VersionSectionProps) => {
  const saved = useSaved(onSaved);
  return (
    <Suspense fallback={<Loading />}>
      <PackChecksFileForm
        workspaceId={workspaceId}
        path={path}
        onSaved={saved}
      />
    </Suspense>
  );
};
