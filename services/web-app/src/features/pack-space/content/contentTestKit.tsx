import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { packStudioApi, type PackVersionModel } from "@entities/pack-studio";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { CONTENT_MODEL, seedContentModel } from "./fixtures";

// Только для тестов области: `renderSpace` на вкладке «Содержимое» с моделью версии в кэше
// запросов. `search` это query адреса без знака вопроса (`doc=nda&seg=terms`).

/**
 * «Править копию» из «Содержимого» зовёт общий `useCopyVersion` (S13): сервер создаёт копию, и
 * экран остаётся на том же месте с новым номером. Подменяет создание копии и отдаёт мок.
 */
export const mockCopyCreated = (version: string) =>
  vi.spyOn(packStudioApi, "createVersion").mockResolvedValue({
    version: {
      pack: "hse-cs-sse",
      template: "coursework",
      version,
      path: `hse-cs-sse/templates/coursework/versions/${version}`,
    },
    base: "2026.1.2",
    update_class: "patch",
    warnings: [],
  });

export const CONTENT_BASE = `${SPACE_BASE}/2026.1.3/content`;

export const renderContent = (
  ui: ReactNode,
  search = "",
  options: {
    model?: PackVersionModel | null;
    version?: string;
    /** Подложить ещё что-то в кэш запросов (дерево файлов и т. п.). */
    before?: (client: QueryClient) => void;
  } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  if (options.model !== null) {
    seedContentModel(client, options.model ?? CONTENT_MODEL);
  }
  options.before?.(client);
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
