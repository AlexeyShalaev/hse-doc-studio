import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { ZodType } from "zod";
import {
  PackLintSchema,
  PackPreviewOptionsSchema,
  PackSubmissionRoutesSchema,
  PackSubmissionSchema,
  PackVersionModelSchema,
  packStudioApi,
  packStudioKeys,
  packSubmissionApi,
} from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { PackFormPane } from "../PackFormPane";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../../contracts/pack-studio/fixtures",
);
const fixture = <T,>(schema: ZodType<T>, dir: string, name: string): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8")),
  );

const MODEL = fixture(PackVersionModelSchema, "PackVersionModel", "editable");
const SUBMISSION = fixture(PackSubmissionSchema, "PackSubmission", "profiles");
const WS = MODEL.workspace_id;
const REF = {
  pack: MODEL.pack,
  template: MODEL.template,
  version: MODEL.version,
};
const PATH = MODEL.manifest.path;

describe("форма версии: раздел «Сдача и подписи»", () => {
  beforeAll(async () => {
    await Promise.all([loadPackFormsNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("раздел открывает форму точек, её правка обновляет модель версии", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(packStudioKeys.model(WS, REF), MODEL);
    const model = vi
      .spyOn(packStudioApi, "versionModel")
      .mockResolvedValue(MODEL);
    vi.spyOn(packSubmissionApi, "get").mockResolvedValue({
      ...SUBMISSION,
      etag: MODEL.manifest.etag,
    });
    vi.spyOn(packSubmissionApi, "routes").mockResolvedValue(
      fixture(
        PackSubmissionRoutesSchema,
        "PackSubmissionRoutes",
        "company_supervisor",
      ),
    );
    vi.spyOn(packStudioApi, "previewOptions").mockResolvedValue(
      fixture(PackPreviewOptionsSchema, "PackPreviewOptions", "coursework"),
    );
    vi.spyOn(packStudioApi, "lint").mockResolvedValue(
      fixture(PackLintSchema, "PackLint", "version"),
    );
    const patch = vi
      .spyOn(packSubmissionApi, "patch")
      .mockResolvedValue({ ...SUBMISSION, etag: '"next"' });
    const onSaved = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <PackFormPane workspaceId={WS} path={PATH} onSaved={onSaved} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByTestId("pf-tab-submission"));
    fireEvent.click(await screen.findByTestId("p0-item-0-method-author-image"));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch.mock.calls[0]?.[3]).toBe(MODEL.manifest.etag);
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith([SUBMISSION.path]);
    });
    await waitFor(() => {
      expect(model).toHaveBeenCalled();
    });
  });
});
