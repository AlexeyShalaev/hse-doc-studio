import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import {
  forgetLegacyUxFlag,
  PACK_STUDIO_PATH,
  withoutUxParam,
} from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import { PackStudioLayout } from "./PackStudioLayout";
import { WorkspacesScreen } from "./WorkspacesScreen";
import "./packStudio.css";

// Экраны пространства (docs/design/pack-studio-ux.md): свой чанк вместе со словарём `packSpace`.
const SpaceApp = lazy(() =>
  import("./space").then((m) => ({ default: m.SpaceApp })),
);

/**
 * Студия шаблонов (/pack-studio/*): своё приложение в том же образе, свой лейаут и lazy-чанк.
 * Пускает охранник по capabilities.pack_studio. Список пространств и экраны пространства
 * (`/w/:ws/t/...`: «Результат», «Содержимое», «Проверка», панель «Изменения»). Старые адреса
 * прежнего вида (`/w/:ws/result/...`, `?file=`, `?view=files`, `?newVersion=`) переводит вход
 * пространства (`legacyToSpace`); параметр `ux` прежнего флага убирается из любого адреса.
 */
export const PackStudioApp = () => {
  const { pathname, search, hash } = useLocation();
  useEffect(forgetLegacyUxFlag, []);
  const clean = withoutUxParam(search);
  if (clean !== null) {
    return <Navigate replace to={`${pathname}${clean}${hash}`} />;
  }
  return (
    <Routes>
      <Route element={<PackStudioLayout />}>
        <Route index element={<WorkspacesScreen />} />
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
        <Route path="*" element={<Navigate to={PACK_STUDIO_PATH} replace />} />
      </Route>
    </Routes>
  );
};
