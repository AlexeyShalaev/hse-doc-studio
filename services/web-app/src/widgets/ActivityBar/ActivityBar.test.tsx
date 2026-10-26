import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { ActivityBar, type ActivityBarProps } from "./ActivityBar";

const base = (over: Partial<ActivityBarProps> = {}): ActivityBarProps => ({
  activity: "documents",
  onSelectActivity: () => undefined,
  onOpenProjectSettings: () => undefined,
  isProjectSettingsActive: false,
  onOpenVersions: () => undefined,
  isVersionsActive: false,
  counts: {
    errors: 0,
    warnings: 0,
    isBuilding: false,
    submitBlockers: 0,
    changedFiles: 4,
  },
  isAgentActive: false,
  onToggleAgent: () => undefined,
  onOpenSystemSettings: () => undefined,
  ...over,
});

const history = () => screen.getByRole("button", { name: /История|History/ });

describe("ActivityBar history badge", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("shows the count of changed files when sync has nothing to say", () => {
    render(<ActivityBar {...base()} />);
    expect(history().querySelector(".activity-badge")?.textContent).toBe("4");
    expect(history().querySelector(".activity-badge.info")).not.toBeNull();
  });

  it("lets a sync badge take its place, with its own tooltip", () => {
    render(
      <ActivityBar
        {...base({
          versionsBadge: { kind: "count", tone: "err", count: 2 },
          versionsTooltip: "История: есть конфликты синхронизации",
        })}
      />,
    );
    const badge = history().querySelector(".activity-badge");
    expect(badge?.textContent).toBe("2");
    expect(badge?.classList.contains("err")).toBe(true);
    expect(history().getAttribute("title")).toBe(
      "История: есть конфликты синхронизации",
    );
    expect(history().textContent).not.toContain("4");
  });
});
