import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { ProjectAccessBanner } from "./ProjectAccessBanner";

describe("ProjectAccessBanner", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("names the mounted template folder when it lags behind the Studio", () => {
    render(
      <ProjectAccessBanner
        templateVersion="2026.1.2"
        access={{
          mode: "read_only",
          reasons: ["template_missing"],
          required_studio: null,
          stale_packs: { path: "/app/packs", studio_version: "0.16.0" },
        }}
      />,
    );

    expect(
      screen.getByText(
        "Версии шаблона 2026.1.2 нет в каталоге шаблонов /app/packs: он подключён извне и отстаёт от Студии v0.16.0. Обновите каталог или уберите подключение.",
      ),
    ).toBeInTheDocument();
    // Студия свежая: совет обновить её был бы неправдой.
    expect(screen.queryByText(/нет в этой версии Студии/)).toBeNull();
    expect(screen.queryByText(/Обновите Студию/)).toBeNull();
    expect(screen.getByText(/О программе/)).toBeInTheDocument();
  });

  it("keeps asking for a newer Studio when the version is missing everywhere", () => {
    render(
      <ProjectAccessBanner
        templateVersion="2027.0"
        access={{
          mode: "read_only",
          reasons: ["template_missing"],
          required_studio: "0.20.0",
          stale_packs: null,
        }}
      />,
    );

    expect(
      screen.getByText(
        "Версии шаблона 2027.0 нет в этой версии Студии (нужна 0.20.0 или новее).",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Обновите Студию/)).toBeInTheDocument();
  });

  it("speaks English for the lagging folder too", async () => {
    await i18n.changeLanguage("en");
    render(
      <ProjectAccessBanner
        templateVersion="2026.1.2"
        access={{
          mode: "read_only",
          reasons: ["template_missing"],
          stale_packs: { path: "/app/packs", studio_version: "0.16.0" },
        }}
      />,
    );

    expect(
      screen.getByText(
        /Template version 2026\.1\.2 is missing from the template folder \/app\/packs: it is mounted from outside and lags behind Studio v0\.16\.0/,
      ),
    ).toBeInTheDocument();
  });
});
