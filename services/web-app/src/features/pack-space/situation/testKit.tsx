import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  packOutcomeKeys,
  type PackOutcomeCompare,
  type PackOutcomeCompareRequest,
} from "@entities/pack-studio";
import {
  COURSEWORK_COMPARE,
  COURSEWORK_INPUTS,
  COURSEWORK_RUN,
  COURSEWORK_SCENARIOS,
} from "@entities/pack-studio/reference";
import { GALLERY_REF, GALLERY_WORKSPACE } from "../galleryKit";

// Только для тестов области: кэш запросов на фикстурах контракта (курсовой проект) и обёртка.

const ID = GALLERY_WORKSPACE.id;

export const seededClient = (
  options: {
    compare?: PackOutcomeCompareRequest;
    /** Ответ сравнения; по умолчанию эталон контракта. */
    data?: PackOutcomeCompare;
  } = {},
): QueryClient => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(packOutcomeKeys.inputs(ID, GALLERY_REF, "work_tree"), {
    ...COURSEWORK_INPUTS,
    workspace_id: ID,
  });
  client.setQueryData(
    packOutcomeKeys.scenarios(
      ID,
      GALLERY_REF.pack,
      GALLERY_REF.template,
      "work_tree",
    ),
    { ...COURSEWORK_SCENARIOS, workspace_id: ID },
  );
  client.setQueryData(
    packOutcomeKeys.scenarioRun(
      ID,
      GALLERY_REF,
      "work_tree",
      COURSEWORK_INPUTS.revision,
    ),
    COURSEWORK_RUN,
  );
  if (options.compare) {
    client.setQueryData(
      packOutcomeKeys.compare(ID, GALLERY_REF, options.compare),
      { data: options.data ?? COURSEWORK_COMPARE, etag: null },
    );
  }
  return client;
};

export const WithClient = ({
  client,
  children,
}: {
  client: QueryClient;
  children: ReactNode;
}) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
