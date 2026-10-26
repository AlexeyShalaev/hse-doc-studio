import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import {
  gitSyncKeys,
  useSyncUiStore,
  type SyncStatusView,
} from "@entities/git-sync";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";
import { PROJECT_ID } from "./connectFixtures";

// Показывает адрес, чтобы тест видел, куда увёл переход.
const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
};

export const renderSettings = (
  ui: ReactElement,
  options: { status?: SyncStatusView; path?: string } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  if (options.status) {
    client.setQueryData(gitSyncKeys.status(PROJECT_ID), options.status);
  }
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[
          options.path ?? `/projects/${PROJECT_ID}/project-settings/sync`,
        ]}
      >
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, client };
};

export const resetSettingsEnvironment = async (): Promise<void> => {
  await i18n.changeLanguage("ru");
  useSyncUiStore.setState({
    popoverOpen: false,
    connectDialog: null,
    command: null,
    toastedSyncIds: {},
  });
  useToastStore.getState().clear();
};

// Radix Select и Popover в jsdom ждут методов, которых там нет.
export const installPointerPolyfills = (): void => {
  const proto = Element.prototype as unknown as Record<string, unknown>;
  proto.hasPointerCapture ??= () => false;
  proto.setPointerCapture ??= () => undefined;
  proto.releasePointerCapture ??= () => undefined;
  proto.scrollIntoView ??= () => undefined;
};
