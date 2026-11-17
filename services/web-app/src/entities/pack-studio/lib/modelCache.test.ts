import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { packOutcomeKeys } from "../api/outcomeQueries";
import { packStudioKeys } from "../api/queries";
import { referenceModel } from "../reference";
import { cacheModelResult, refreshAfterFileWrite } from "./modelCache";

const REF = { pack: "hse-cs-sse", template: "coursework", version: "2026.1.6" };

describe("кэш после записи манифеста", () => {
  it("ответ правки ложится в модель, а расчёт результата версии устаревает", () => {
    const client = new QueryClient();
    const model = referenceModel("w1", REF.pack, REF.template, REF.version, [
      "hse-cs-sse/templates/coursework/versions/2026.1.6/version.yaml",
    ]);
    client.setQueryData(packOutcomeKeys.result("w1", REF, {}), {
      stale: false,
    });
    cacheModelResult(client, "w1", REF, model);
    expect(client.getQueryData(packStudioKeys.model("w1", REF))).toEqual(model);
    expect(
      client.getQueryState(packOutcomeKeys.result("w1", REF, {}))
        ?.isInvalidated,
    ).toBe(true);
    // Объяснение лежит под тем же префиксом версии: оно тоже перечитывается.
    client.setQueryData(
      packOutcomeKeys.explain("w1", REF, {
        element: { section: "documents", id: "x" },
      }),
      {},
    );
    cacheModelResult(client, "w1", REF, model);
    expect(
      client.getQueryState(
        packOutcomeKeys.explain("w1", REF, {
          element: { section: "documents", id: "x" },
        }),
      )?.isInvalidated,
    ).toBe(true);
  });

  it("запись файла целиком перечитывает модель и ждёт её", async () => {
    const client = new QueryClient();
    let reads = 0;
    await client.prefetchQuery({
      queryKey: packStudioKeys.model("w1", REF),
      queryFn: () => {
        reads += 1;
        return Promise.resolve({ read: reads });
      },
    });
    client.setQueryData(packOutcomeKeys.result("w1", REF, {}), {});
    await refreshAfterFileWrite(
      client,
      "w1",
      REF,
      "hse-cs-sse/templates/coursework/versions/2026.1.6/version.yaml",
    );
    expect(reads).toBe(2);
    expect(client.getQueryData(packStudioKeys.model("w1", REF))).toEqual({
      read: 2,
    });
    expect(
      client.getQueryState(packOutcomeKeys.result("w1", REF, {}))
        ?.isInvalidated,
    ).toBe(true);
  });
});
