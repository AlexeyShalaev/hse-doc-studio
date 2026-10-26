import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { useSyncUiStore, type ConnectDialogMode } from "@entities/git-sync";
import { useToastStore } from "@shared/lib";
import { i18n } from "@shared/lib/i18n";

export const makeClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });

export const renderWithClient = (
  ui: ReactElement,
  client: QueryClient = makeClient(),
): RenderResult & { client: QueryClient } => ({
  ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  client,
});

export const resetConnectEnvironment = async (): Promise<void> => {
  await i18n.changeLanguage("ru");
  useSyncUiStore.setState({
    popoverOpen: false,
    connectDialog: null,
    command: null,
    toastedSyncIds: {},
  });
  useToastStore.getState().clear();
};

export const openConnectDialog = (
  mode: ConnectDialogMode = "connect",
): void => {
  useSyncUiStore.setState({ connectDialog: { mode } });
};
