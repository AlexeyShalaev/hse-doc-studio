import { describe, expect, it } from "vitest";
import { artifactFileUrl } from "./artifactApi";

describe("artifactFileUrl", () => {
  it("keeps the backend path, which already starts with /api/v1", () => {
    expect(artifactFileUrl("/api/v1/projects/p/artifacts/a/file")).toMatch(
      /\/api\/v1\/projects\/p\/artifacts\/a\/file$/,
    );
  });
});
