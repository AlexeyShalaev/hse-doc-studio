import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { renderSpace, SPACE_BASE } from "../spaceTestKit";
import { deltaStore } from "./deltaStore";
import { SituationBar } from "./SituationBar";
import { seededClient, WithClient } from "./testKit";

const URL = `${SPACE_BASE}/2026.1.3/result`;
const location = () => screen.getByTestId("location").textContent;
const show = (search = "") =>
  renderSpace(
    <WithClient client={seededClient()}>
      <SituationBar />
    </WithClient>,
    `${URL}${search}`,
  );

describe("SituationBar", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  beforeEach(() => {
    deltaStore.reset();
  });
  afterEach(cleanup);

  it("три условия кнопками и «Ещё N условий»", () => {
    show();
    const bar = screen.getByTestId("sp-situation");
    expect(within(bar).getAllByTestId(/^sp-sit-chip-/)).toHaveLength(3);
    expect(within(bar).getByTestId("sp-sit-chip-kind")).toHaveTextContent(
      "Вид работы Проектная",
    );
    expect(screen.getByTestId("sp-sit-more-btn")).toHaveTextContent(
      "Ещё 6 условий",
    );
  });

  it("условие меняется за два клика, значение уходит в адрес", () => {
    show();
    fireEvent.click(screen.getByTestId("sp-sit-chip-kind"));
    expect(screen.getByTestId("sp-sit-affects")).toHaveTextContent(
      "Что это меняет: Документы",
    );
    fireEvent.click(screen.getByTestId("sp-sit-value-kind-research"));
    expect(location()).toContain("i.kind=research");
    expect(screen.getByTestId("sp-sit-chip-kind")).toHaveAttribute(
      "data-changed",
      "true",
    );
    expect(screen.queryByTestId("sp-sit-affects")).not.toBeInTheDocument();
  });

  it("«Вернуть» снимает изменение из адреса", () => {
    show("?i.kind=research");
    fireEvent.click(screen.getByTestId("sp-sit-chip-kind"));
    fireEvent.click(screen.getByTestId("sp-sit-restore"));
    expect(location()).not.toContain("i.kind");
  });

  it("условие из окна «Ещё» встаёт на полосу", () => {
    show();
    fireEvent.click(screen.getByTestId("sp-sit-more-btn"));
    const dialog = screen.getByTestId("sp-sit-more");
    expect(
      within(dialog).getByText("Не влияют на этот шаблон"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByTestId("sp-sit-value-co_supervisor-yes"),
    );
    expect(location()).toContain("i.co_supervisor=yes");
    expect(
      within(screen.getByTestId("sp-situation")).getByTestId(
        "sp-sit-chip-co_supervisor",
      ),
    ).toHaveAttribute("data-changed", "true");
  });

  it("готовый случай ставит свои условия; без него условия сбрасываются", () => {
    show("?i.kind=research");
    fireEvent.click(screen.getByTestId("sp-sit-cases"));
    expect(screen.getByTestId("sp-sit-case-company-supervisor")).toBeVisible();
    expect(screen.getByTestId("sp-sit-case-draft")).toBeDisabled();
    fireEvent.click(screen.getByTestId("sp-sit-case-company-supervisor"));
    expect(location()).toContain("case=company-supervisor");
    expect(location()).not.toContain("i.kind");
    expect(screen.getByTestId("sp-sit-cases")).toHaveTextContent(
      "Научрук из компании, есть консультант",
    );
  });

  it("меню «Ещё»: сбросить, запомнить, сравнить", async () => {
    show("?i.kind=research&case=company-supervisor");
    fireEvent.pointerDown(screen.getByTestId("sp-sit-menu"), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByTestId("sp-sit-menu-reset"));
    expect(location()).not.toContain("case=");
    expect(location()).not.toContain("i.kind");
  });

  it("меню «Ещё»: сравнение уходит в «Проверку» с теми же условиями", async () => {
    show("?i.kind=research");
    fireEvent.pointerDown(screen.getByTestId("sp-sit-menu"), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByTestId("sp-sit-menu-compare"));
    expect(location()).toContain("/check?");
    expect(location()).toContain("compare=1");
    expect(location()).toContain("i.kind=research");
  });
});
