import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CompileDetailSchema } from "./documentSchemas";

const placement = (name: string): unknown =>
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../../../..",
        "contracts/server/fixtures/CompilePlacement",
        `${name}.json`,
      ),
      "utf8",
    ),
  );

const detail = {
  id: "c1",
  status: "running",
  engine: "xelatex",
  started_at: "2026-10-30T10:00:00Z",
  warnings: 0,
  errors: 0,
};

describe("CompileDetailSchema", () => {
  it("keeps the server placement of the build", () => {
    const parsed = CompileDetailSchema.parse({
      ...detail,
      placement: placement("shared_offline"),
    });
    expect(parsed.placement).toEqual({
      state: "shared",
      runner_name: null,
      runner_owner: null,
      fallback: "offline",
      wait_s: null,
    });
  });

  it("accepts a local build without placement", () => {
    expect(CompileDetailSchema.parse(detail).placement).toBeUndefined();
  });
});
