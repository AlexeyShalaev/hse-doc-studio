import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import type { CheckpointReadiness } from "@entities/submission";
import type { RouteTally } from "@features/signing-route-progress";
import { CheckpointHero } from "./CheckpointHero";

// Шапка точки: при идущем маршруте рядом со счётом подписей видно, сколько согласовано.

const READINESS: CheckpointReadiness = {
  done: 2,
  total: 5,
  breakdown: {
    documents: { done: 2, total: 2 },
    signatures: { done: 0, total: 3 },
    forms: { done: 0, total: 0 },
  },
  isComplete: false,
  isUnknown: false,
  items: [],
  formIds: [],
  blockers: 3,
};

const TALLY: RouteTally = {
  approved: 1,
  done: 0,
  total: 3,
  optionalApproved: 0,
  optionalDone: 0,
  optionalTotal: 1,
};

const mount = (routeTally: RouteTally | null) =>
  render(
    <I18nextProvider i18n={i18n}>
      <CheckpointHero
        name="Тема КП"
        description=""
        readiness={READINESS}
        isPacked={false}
        routeTally={routeTally}
      />
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

describe("CheckpointHero", () => {
  it("маршрут идёт: «0/3 подписи» и «1/3 согласовано», кольцо по подписям", () => {
    mount(TALLY);
    const note = screen.getByTestId("checkpoint-route-approved");
    expect(note).toHaveTextContent("1/3 согласовано");
    expect(note.parentElement).toHaveTextContent("0/3Подписи1/3 согласовано");
    expect(note.parentElement).toHaveAttribute(
      "title",
      "Подписано 0 из 3, согласовано 1 из 3",
    );
    // Кольцо и общий счёт не меняются: согласование не подпись.
    expect(screen.getAllByText("Готово 2 из 5").length).toBeGreaterThan(0);
  });

  it("маршрута нет: только подписи", () => {
    mount(null);
    expect(screen.queryByTestId("checkpoint-route-approved")).toBeNull();
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    mount(TALLY);
    expect(screen.getByTestId("checkpoint-route-approved")).toHaveTextContent(
      "1/3 approved",
    );
  });
});
