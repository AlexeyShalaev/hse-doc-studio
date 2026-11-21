import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { ApiError } from "@shared/api";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { COURSEWORK_SCENARIOS } from "@entities/pack-studio/reference";
import { packOutcomeApi } from "@entities/pack-studio";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { deltaStore } from "./deltaStore";
import { SituationBar } from "./SituationBar";
import { seededClient, WithClient } from "./testKit";

const location = () => screen.getByTestId("location").textContent;

const open = (search: string) => {
  renderSpace(
    <WithClient client={seededClient()}>
      <SituationBar />
    </WithClient>,
    `${SPACE_BASE}/2026.1.3/result${search}`,
  );
  fireEvent.pointerDown(screen.getByTestId("sp-sit-menu"), {
    button: 0,
    ctrlKey: false,
  });
};
const openDialog = async (search: string) => {
  open(search);
  fireEvent.click(await screen.findByTestId("sp-sit-menu-save"));
};

describe("«Запомнить этот случай»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    deltaStore.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("одно поле на виду; снимок результата под «Дополнительно»", async () => {
    await openDialog("?i.kind=research");
    const dialog = screen.getByTestId("sp-sit-save");
    expect(dialog).toHaveTextContent("В случай войдёт 1 условие");
    expect(screen.getByTestId("sp-sit-save-name")).toBeVisible();
    expect(
      screen.getByText("Дополнительно").closest("details"),
    ).not.toHaveAttribute("open");
  });

  it("без названия не записывает", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    await openDialog("");
    fireEvent.click(screen.getByTestId("sp-sit-save-submit"));
    expect(put).not.toHaveBeenCalled();
    expect(await screen.findByText("Укажите название")).toBeInTheDocument();
  });

  it("записывает условия с экрана и выбирает новый случай", async () => {
    const entry = {
      ...COURSEWORK_SCENARIOS.scenarios[0]!,
      id: "nda-dva-avtora",
    };
    const put = vi
      .spyOn(packOutcomeApi, "putScenario")
      .mockResolvedValue(entry);
    await openDialog("?i.kind=research&case=company-supervisor");
    fireEvent.change(screen.getByTestId("sp-sit-save-name"), {
      target: { value: "NDA, два автора" },
    });
    fireEvent.click(screen.getByTestId("sp-sit-save-submit"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [, , , scenario, body, ifMatch] = put.mock.calls[0]!;
    expect(scenario).toBe("nda-dva-avtora");
    expect(ifMatch).toBeNull();
    expect(body.scenario.name).toEqual({ ru: "NDA, два автора" });
    // условия выбранного случая и изменения поверх него
    expect(body.scenario.inputs).toEqual({
      supervisor: "company",
      co_supervisor: "yes",
      kind: "research",
    });
    expect(body.record_snapshot).toBe("work_tree");
    await waitFor(() => {
      expect(location()).toContain("case=nda-dva-avtora");
    });
    expect(location()).not.toContain("i.kind");
  });

  it("отказ сервера: понятная строка, окно остаётся", async () => {
    vi.spyOn(packOutcomeApi, "putScenario").mockRejectedValue(
      new ApiError("Занято", "scenario_taken", 409),
    );
    await openDialog("");
    fireEvent.change(screen.getByTestId("sp-sit-save-name"), {
      target: { value: "Случай" },
    });
    fireEvent.click(screen.getByTestId("sp-sit-save-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Случай с таким именем уже есть",
    );
    expect(screen.getByTestId("sp-sit-save")).toBeVisible();
  });
});
