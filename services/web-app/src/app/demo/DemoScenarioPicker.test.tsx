import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { DemoScenarioPicker } from "./DemoScenarioPicker";
import { useDemoScenarioStore } from "./scenarioStore";
import { SCENARIOS } from "./scenarios";

const renderPicker = (client = new QueryClient()) =>
  render(
    <QueryClientProvider client={client}>
      <DemoScenarioPicker />
    </QueryClientProvider>,
  );

describe("DemoScenarioPicker", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    useDemoScenarioStore.setState({ scenarioId: "not_connected" });
  });

  it("shows the current scenario on the button", () => {
    renderPicker();
    expect(
      screen.getByRole("button", { name: "Демо-сценарии синхронизации" }),
    ).toHaveTextContent("Репозиторий не подключён");
  });

  it("lists every scenario with a hint and switches on click", async () => {
    const user = userEvent.setup();
    const client = new QueryClient();
    renderPicker(client);
    await user.click(
      screen.getByRole("button", { name: "Демо-сценарии синхронизации" }),
    );
    for (const scenario of SCENARIOS) {
      // Текущий сценарий виден и на кнопке, и в списке.
      expect(
        (
          await screen.findAllByText(
            i18n.t(`gitSync:demo.scenario.${scenario.id}.title`),
          )
        ).length,
      ).toBeGreaterThan(0);
    }
    await user.click(screen.getByText("Конфликты ждут решения"));
    expect(useDemoScenarioStore.getState().scenarioId).toBe("conflicts");
  });
});

describe("demo copy", () => {
  it.each(["ru", "en"])(
    "has a title and hint for every scenario in %s",
    (lng) => {
      const t = i18n.getFixedT(lng);
      for (const scenario of SCENARIOS) {
        expect(
          i18n.exists(`gitSync:demo.scenario.${scenario.id}.title`, { lng }),
        ).toBe(true);
        expect(t(`gitSync:demo.scenario.${scenario.id}.hint`)).not.toContain(
          "demo.scenario",
        );
      }
    },
  );
});
