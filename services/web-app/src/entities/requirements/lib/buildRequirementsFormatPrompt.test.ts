import { describe, expect, it } from "vitest";

import { buildRequirementsFormatPrompt } from "./buildRequirementsFormatPrompt";

describe("buildRequirementsFormatPrompt", () => {
  it("steers the agent through preview → apply with the project tools", () => {
    const prompt = buildRequirementsFormatPrompt("id");

    expect(prompt).toContain("preview_requirements_format");
    expect(prompt).toContain("set_requirements_format");
    expect(prompt).toContain("grep_project");
  });

  it("names the currently active format", () => {
    expect(buildRequirementsFormatPrompt("macro")).toContain("Макросы");
    expect(buildRequirementsFormatPrompt("id")).toContain("ID-паттерн");
    expect(buildRequirementsFormatPrompt("custom")).toContain("Свои regex");
  });
});
