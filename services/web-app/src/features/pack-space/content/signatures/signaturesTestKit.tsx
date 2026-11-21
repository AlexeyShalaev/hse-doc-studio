import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { renderSpace, SPACE_BASE } from "../../spaceTestKit";
import { CONTENT_MODEL, RELEASED_MODEL, seedContentModel } from "../fixtures";
import { seedSignatures } from "./fixtures";

// Только для тестов «Подписей»: экран «Содержимое» с моделью версии, условиями сборки, готовой
// сборкой и подписями в кэше запросов, как будто сервер уже ответил.

export const renderSignatures = (
  ui: ReactNode,
  search: string,
  options: {
    released?: boolean;
    seed?: Parameters<typeof seedSignatures>[1];
    /** Свои данные поверх подложенных (до первого кадра). */
    before?: (client: QueryClient) => void;
  } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  const version = options.released ? "2026.1.2" : "2026.1.3";
  seedContentModel(client, options.released ? RELEASED_MODEL : CONTENT_MODEL);
  seedSignatures(client, {
    ref: { pack: "hse-cs-sse", template: "coursework", version },
    ...options.seed,
  });
  options.before?.(client);
  const result = renderSpace(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    `${SPACE_BASE}/${version}/content?${search}`,
  );
  return Object.assign(result, { client });
};
