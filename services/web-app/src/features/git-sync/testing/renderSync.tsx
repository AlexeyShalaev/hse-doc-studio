import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import {
  gitSyncKeys,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";

export const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

export const makeClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });

// Показывает адрес, чтобы тест видел, куда увёл переход.
const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

export const renderSync = (
  ui: ReactElement,
  options: {
    client?: QueryClient;
    status?: SyncStatusView;
    path?: string;
  } = {},
): RenderResult & { client: QueryClient } => {
  const client = options.client ?? makeClient();
  if (options.status) {
    client.setQueryData(gitSyncKeys.status(PROJECT_ID), options.status);
  }
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[options.path ?? `/projects/${PROJECT_ID}/documents`]}
      >
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
};

export const resetSyncEnvironment = async (): Promise<void> => {
  await i18n.changeLanguage("ru");
  useSyncUiStore.setState({
    popoverOpen: false,
    connectDialog: null,
    bundleDialogOpen: false,
    profileDialogOpen: false,
    command: null,
    toastedSyncIds: {},
  });
  try {
    sessionStorage.clear();
  } catch {
    // нет хранилища: тесту оно не нужно
  }
};
