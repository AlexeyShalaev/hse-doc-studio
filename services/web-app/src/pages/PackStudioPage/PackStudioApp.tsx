import { Navigate, Route, Routes } from "react-router";
import { PACK_STUDIO_PATH } from "@entities/pack-studio";
import { PackStudioLayout } from "./PackStudioLayout";
import { WorkspaceScreen } from "./WorkspaceScreen";
import { WorkspacesScreen } from "./WorkspacesScreen";
import "./packStudio.css";

/**
 * Студия шаблонов (/pack-studio/*, template-studio.md, раздел 3): своё
 * приложение в том же образе, свой лейаут и lazy-чанк. Пускает охранник по
 * capabilities.pack_studio; словарь packStudio он же подключает заранее.
 */
export const PackStudioApp = () => (
  <Routes>
    <Route element={<PackStudioLayout />}>
      <Route index element={<WorkspacesScreen />} />
      <Route path="w/:workspaceId" element={<WorkspaceScreen />} />
      <Route path="*" element={<Navigate to={PACK_STUDIO_PATH} replace />} />
    </Route>
  </Routes>
);
