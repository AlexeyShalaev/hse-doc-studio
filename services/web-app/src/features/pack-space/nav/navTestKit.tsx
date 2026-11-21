import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router";
import { isSpaceTab, type PackTree } from "@entities/pack-studio";
import { SpaceProvider } from "../context/SpaceContext";
import { GALLERY_WORKSPACE } from "../galleryKit";
import { SPACE_BASE } from "../spaceTestKit";
import { TREE, seedNav } from "./fixtures";

// Только для тестов области nav: пространство на дереве с двумя паками, кэш запросов с git и
// настоящий роутер в памяти. `renderSpace` каркаса знает одно дерево без паков для переключения.

const Provider = ({
  tree,
  children,
}: {
  tree: PackTree;
  children: ReactNode;
}) => {
  const { pack = "", template = "", version = "", tab } = useParams();
  return (
    <SpaceProvider
      workspace={GALLERY_WORKSPACE}
      tree={tree}
      versionRef={{ pack, template, version }}
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

export const DRAFT_URL = `${SPACE_BASE}/2026.1.3/result`;
export const RELEASED_URL = `${SPACE_BASE}/2026.1.2/result`;

export const renderNav = (
  ui: ReactNode,
  {
    url = DRAFT_URL,
    changed = [],
    tree = TREE,
  }: { url?: string; changed?: string[]; tree?: PackTree } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seedNav(changed)(client);
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route
            path="/pack-studio/w/:workspaceId/t/:pack/:template/:version/:tab"
            element={<Provider tree={tree}>{ui}</Provider>}
          />
        </Routes>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return Object.assign(result, { client });
};
