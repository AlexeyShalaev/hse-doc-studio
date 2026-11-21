import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { PACK_STUDIO_PATH, usePackStudioUx } from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import { PackStudioLayout } from "./PackStudioLayout";
import { OutcomeEntry, OutcomeRoute } from "./OutcomeRoute";
import { WorkspaceEntry } from "./WorkspaceEntry";
import { WorkspacesScreen } from "./WorkspacesScreen";
import "./packStudio.css";

// Новый интерфейс (docs/design/pack-studio-ux.md): свой чанк, грузится только при `?ux=2`.
const SpaceApp = lazy(() =>
  import("./space").then((m) => ({ default: m.SpaceApp })),
);

/**
 * Студия шаблонов (/pack-studio/*, template-studio.md, раздел 3): своё
 * приложение в том же образе, свой лейаут и lazy-чанк. Пускает охранник по
 * capabilities.pack_studio; словарь packStudio он же подключает заранее. Пространство открывается
 * на экране «Результат» (features/pack-outcome); режим «Файлы» это `?view=files` и `?file=`.
 * С флагом `?ux=2` вместо этого новый интерфейс (features/pack-space, pages/PackStudioPage/space).
 */
export const PackStudioApp = () => {
  // Единственное место, где читается флаг: без `?ux=2` приложение ведёт себя как раньше.
  const ux = usePackStudioUx();
  return (
    <Routes>
      <Route element={<PackStudioLayout />}>
        <Route index element={<WorkspacesScreen />} />
        {ux === 2 ? (
          <Route
            path="w/:workspaceId/*"
            element={
              <Suspense
                fallback={
                  <div className="ps-page flex justify-center">
                    <Spinner size="lg" />
                  </div>
                }
              >
                <SpaceApp />
              </Suspense>
            }
          />
        ) : (
          <>
            <Route path="w/:workspaceId" element={<WorkspaceEntry />} />
            <Route path="w/:workspaceId/result" element={<OutcomeEntry />} />
            <Route
              path="w/:workspaceId/result/:pack/:template/:version"
              element={<OutcomeRoute />}
            />
          </>
        )}
        <Route path="*" element={<Navigate to={PACK_STUDIO_PATH} replace />} />
      </Route>
    </Routes>
  );
};
