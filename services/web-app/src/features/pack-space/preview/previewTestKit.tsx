import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";
import { packStudioKeys, type PackDiagnostic } from "@entities/pack-studio";
import {
  CONTENT_TEXT_PATH,
  CONTENT_VERSION_DIR,
  seedContentModel,
  seedContentText,
} from "../content/fixtures";
import { GALLERY_WORKSPACE } from "../galleryKit";
import { SPACE_BASE, renderSpace } from "../spaceTestKit";
import { seedPreview, type PreviewSeed } from "./fixtures";

// Только для тестов предпросмотра: `renderSpace` на вкладке «Содержимое» или «Результат» с моделью
// версии, результатом, параметрами сборки и (по желанию) готовой сборкой в кэше запросов.
// `search` это query адреса без знака вопроса (`doc=technical_specification&i.kind=research`).

export const renderPreview = (
  ui: ReactNode,
  search = "",
  options: {
    tab?: "content" | "result";
    seed?: PreviewSeed;
    /** Свои данные поверх подложенных (до первого кадра). */
    before?: (client: QueryClient) => void;
  } = {},
): RenderResult & { client: QueryClient } => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seedContentModel(client);
  seedPreview(client, { search, ...options.seed });
  options.before?.(client);
  const base = `${SPACE_BASE}/2026.1.3/${options.tab ?? "content"}`;
  const result = renderSpace(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    search ? `${base}?${search}` : base,
  );
  return Object.assign(result, { client });
};

/** Замечание проверки версии к файлу (по умолчанию к тексту «Технического задания»). */
export const finding = (
  line: number | null,
  severity: PackDiagnostic["severity"],
  message: string,
  path: string = CONTENT_TEXT_PATH,
): PackDiagnostic => ({
  severity,
  check: "lint",
  message,
  path,
  line,
  pointer: null,
});

/** Текст файла, подсказки и проверка версии с этими замечаниями (для `before`). */
export const withLint =
  (findings: PackDiagnostic[]) =>
  (client: QueryClient): void => {
    seedContentText(client);
    client.setQueryData(
      packStudioKeys.lint(GALLERY_WORKSPACE.id, CONTENT_VERSION_DIR, "0"),
      {
        scope: "version",
        target: CONTENT_VERSION_DIR,
        released: false,
        errors: findings.filter((item) => item.severity === "error").length,
        warnings: findings.filter((item) => item.severity === "warning").length,
        findings,
      },
    );
  };
