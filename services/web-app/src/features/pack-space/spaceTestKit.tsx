import { render, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router";
import { isSpaceTab } from "@entities/pack-studio";
import { SpaceProvider } from "./context/SpaceContext";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "./galleryKit";

// Только для тестов: настоящий роутер в памяти и `SpaceProvider` на фикстурах галереи, как
// в `SpaceRoute`. Адрес по умолчанию: версия 2026.1.3 (черновик), вкладка «Результат».

export const SPACE_BASE = "/pack-studio/w/gallery-ws/t/hse-cs-sse/coursework";

const Provider = ({ children }: { children: ReactNode }) => {
  const { version = "", tab } = useParams<{ version: string; tab: string }>();
  return (
    <SpaceProvider
      workspace={GALLERY_WORKSPACE}
      tree={GALLERY_TREE}
      versionRef={{ pack: "hse-cs-sse", template: "coursework", version }}
      tab={isSpaceTab(tab) ? tab : "result"}
    >
      {children}
    </SpaceProvider>
  );
};

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

export const renderSpace = (
  ui: ReactNode,
  url = `${SPACE_BASE}/2026.1.3/result`,
): RenderResult =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/pack-studio/w/:workspaceId/t/:pack/:template/:version/:tab"
          element={<Provider>{ui}</Provider>}
        />
      </Routes>
      <Probe />
    </MemoryRouter>,
  );
