import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { sessionKeys, type Bootstrap } from "@entities/session";
import type { BuildBlock } from "@entities/compile";
import { BuildBlockedNotice } from "./index";

const SERVER = JSON.parse(
  readFileSync(
    join(
      import.meta.dirname,
      "../../../../..",
      "contracts/server/fixtures/Bootstrap/server_user.json",
    ),
    "utf8",
  ),
) as Bootstrap;

const PROJECT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b";

const mount = (block: BuildBlock, admin: boolean) => {
  const client = new QueryClient();
  client.setQueryData(sessionKeys.bootstrap(), {
    ...SERVER,
    capabilities: { ...SERVER.capabilities, admin },
  });
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>
          <BuildBlockedNotice block={block} projectId={PROJECT} />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
};

describe("BuildBlockedNotice", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("no runners: suggests the desktop Studio and the administrator", () => {
    mount({ reason: "no_runners", tags: ["tex"] }, false);
    const box = screen.getByTestId("build-blocked-notice");
    expect(box.textContent).toContain("Облачная сборка сейчас недоступна");
    expect(box.textContent).toContain("не подключён ни один раннер");
    expect(box.textContent).toContain("Студии на компьютере");
    expect(box.textContent).toContain("попросите администратора");
    expect(
      screen.queryByTestId("build-blocked-runners-link"),
    ).not.toBeInTheDocument();
  });

  it("offers to build locally in the desktop Studio for this project", () => {
    mount({ reason: "no_runners", tags: ["tex"] }, false);
    const link = screen.getByTestId("local-studio-link");
    expect(link).toHaveTextContent("Собрать локально");
    expect(link).toHaveAttribute("href", `/local-studio?project=${PROJECT}`);
  });

  it("missing office runner: names the kind of documents", () => {
    mount({ reason: "no_runner_for_tags", tags: ["office"] }, false);
    expect(screen.getByTestId("build-blocked-notice").textContent).toContain(
      "Нет подключённого раннера для офисных документов",
    );
  });

  it("administrator gets a link to the Runners page", () => {
    mount({ reason: "no_runners", tags: ["tex"] }, true);
    expect(screen.getByTestId("build-blocked-runners-link")).toHaveAttribute(
      "href",
      "/admin/runners",
    );
  });

  it("speaks English too", async () => {
    await i18n.changeLanguage("en");
    mount({ reason: "no_runners", tags: ["tex"] }, false);
    expect(screen.getByTestId("build-blocked-notice").textContent).toContain(
      "Cloud build is unavailable right now",
    );
  });
});
