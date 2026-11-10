import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { signingRouteKeys } from "../api/signingRouteQueries";
import {
  createGuardMemory,
  type GuardDoc,
  type GuardMemory,
} from "../lib/editGuard";
import type { SigningRouteSummary } from "../model/signingRoute.schema";
import { RouteEditGuardProvider } from "../ui/RouteEditGuard";
import { SR_DOC, SR_PROJECT_ID, SR_REVIEW_DOC } from "./fixtures";

// Обвязка тестов мест правки: провайдер мягкого предупреждения поверх засеянного списка
// маршрутов, без сети. Отдельный файл, чтобы React-обвязка не попадала в демо-сборку.

export const GUARD_DOCS: GuardDoc[] = [
  {
    id: SR_DOC.doc_id,
    name: SR_DOC.name.ru,
    folder: SR_DOC.doc_id,
  },
  {
    id: SR_REVIEW_DOC.doc_id,
    name: SR_REVIEW_DOC.name.ru,
    folder: SR_REVIEW_DOC.doc_id,
  },
];

/** Память без `sessionStorage`: каждый тест начинает с чистого сеанса. */
export const freshGuardMemory = (): GuardMemory =>
  createGuardMemory(() => null);

export type GuardHarness = {
  client: QueryClient;
  memory: GuardMemory;
  wrapper: ({ children }: { children: ReactNode }) => ReactNode;
};

export const makeGuardHarness = ({
  routes,
  projectId = SR_PROJECT_ID,
  docs = GUARD_DOCS,
  memory = freshGuardMemory(),
  client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  }),
}: {
  routes: SigningRouteSummary[];
  projectId?: string;
  docs?: GuardDoc[];
  memory?: GuardMemory;
  client?: QueryClient;
}): GuardHarness => {
  client.setQueryData(signingRouteKeys.list(projectId, null), {
    items: routes,
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <RouteEditGuardProvider
        projectId={projectId}
        enabled
        docs={docs}
        memory={memory}
      >
        {children}
      </RouteEditGuardProvider>
    </QueryClientProvider>
  );
  return { client, memory, wrapper };
};
