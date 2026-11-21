import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import type { PackVersionModel } from "@entities/pack-studio";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { CONTENT_MODEL, seedContentModel } from "./fixtures";

// Только для тестов области: `renderSpace` на вкладке «Содержимое» с моделью версии в кэше
// запросов. `search` это query адреса без знака вопроса (`doc=nda&seg=terms`).

export const CONTENT_BASE = `${SPACE_BASE}/2026.1.3/content`;

export const renderContent = (
  ui: ReactNode,
  search = "",
  options: { model?: PackVersionModel | null; version?: string } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (options.model !== null) {
    seedContentModel(client, options.model ?? CONTENT_MODEL);
  }
  const base = options.version
    ? `${SPACE_BASE}/${options.version}/content`
    : CONTENT_BASE;
  const url = search ? `${base}?${search}` : base;
  const result = renderSpace(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    url,
  );
  return Object.assign(result, { client });
};
