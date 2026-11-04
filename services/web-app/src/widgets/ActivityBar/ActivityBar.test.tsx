import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { installViewport } from "@shared/lib/viewport/testing";
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

describe("ActivityBar on a phone", () => {
  let viewport: ReturnType<typeof installViewport> | undefined;
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    viewport?.restore();
    viewport = undefined;
  });

  it("is a bottom tab bar with four modes and a «More» tab", () => {
    viewport = installViewport(390);
    render(<ActivityBar {...base()} />);
    const bar = screen.getByRole("navigation");
    expect(bar).toHaveClass("activity-bar--tabs");
    const tabs = within(bar).getAllByRole("button");
    expect(tabs.map((tab) => tab.textContent?.replace(/\d+$/, ""))).toEqual([
      "Документы",
      "Замечания",
      "Сдача",
      "Файлы",
      "Ещё",
    ]);
  });

  it("moves project settings, history, agent and system settings into the «More» sheet", async () => {
    viewport = installViewport(390);
    const calls: string[] = [];
    render(
      <ActivityBar
        {...base({
          onOpenProjectSettings: () => calls.push("settings"),
          onOpenVersions: () => calls.push("history"),
          onToggleAgent: () => calls.push("agent"),
          onOpenSystemSettings: () => calls.push("system"),
        })}
      />,
    );
    const user = userEvent.setup();
    expect(screen.queryByTestId("activity-more")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Ещё/ }));
    const sheet = screen.getByTestId("activity-more");
    expect(within(sheet).getAllByRole("button")).toHaveLength(4);
    await user.click(screen.getByTestId("activity-more-versions"));
    // Выбор закрывает шторку и делает своё дело.
    expect(calls).toEqual(["history"]);
    expect(screen.queryByTestId("activity-more")).not.toBeInTheDocument();
  });

  it("hides the rows a link visitor may not use", async () => {
    viewport = installViewport(390);
    render(
      <ActivityBar
        {...base({ hidden: ["submit", "projectSettings", "agent"] })}
      />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: /Ещё/ }));
    expect(screen.queryByTestId("activity-more-projectSettings")).toBeNull();
    expect(screen.queryByTestId("activity-more-agent")).toBeNull();
    expect(screen.getByTestId("activity-more-versions")).toBeInTheDocument();
  });

  it("puts the sync badge of the history row on the «More» tab", () => {
    viewport = installViewport(390);
    render(
      <ActivityBar
        {...base({ versionsBadge: { kind: "count", tone: "err", count: 2 } })}
      />,
    );
    const more = screen.getByRole("button", { name: /Ещё/ });
    expect(more.querySelector(".activity-badge.err")?.textContent).toBe("2");
  });

  it("keeps the vertical rail on a desktop", () => {
    viewport = installViewport(1360);
    render(<ActivityBar {...base()} />);
    expect(screen.getByRole("navigation")).not.toHaveClass(
      "activity-bar--tabs",
    );
    expect(screen.queryByRole("button", { name: /Ещё/ })).toBeNull();
  });
});
