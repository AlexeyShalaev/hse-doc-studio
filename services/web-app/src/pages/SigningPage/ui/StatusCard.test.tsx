import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { loadSigningNamespace } from "@shared/lib/i18n/signingNamespace";
import type { SigningTask } from "@entities/signing-route";
import { makeSigningTask } from "@entities/signing-route/testing";
import type { SigningPerson, SigningStatus } from "../lib/signingState";
import { StatusCard } from "./StatusCard";

// Имя с инициалами само кончается точкой: в конце фразы вторая не нужна («П. П..»).
const PETROV: SigningPerson = { name: "Петров П. П.", persona: "supervisor" };
const IVANOV: SigningPerson = { name: "Иванов Иван", persona: "author" };

/** Задача, где смотрящий не участник шага: строка «кто сейчас» берётся из `status`. */
const outsider = (): SigningTask => {
  const task = makeSigningTask();
  return {
    ...task,
    steps: task.steps.map((step) => step.map((p) => ({ ...p, me: false }))),
  };
};

const mount = (status: SigningStatus) =>
  render(
    <I18nextProvider i18n={i18n}>
      <StatusCard task={outsider()} status={status} />
    </I18nextProvider>,
  );

const lines = () =>
  Array.from(screen.getByTestId("signing-status").querySelectorAll("p")).map(
    (p) => p.textContent,
  );

beforeAll(async () => {
  await loadSigningNamespace();
});

describe("StatusCard: имя с инициалами в конце фразы", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("«Следующим подписывает Петров П. П.» без второй точки", () => {
    mount({ kind: "done", next: [PETROV] });
    expect(lines()).toEqual(["Следующим подписывает Петров П. П."]);
  });

  it("несколько следующих: точка одна, после обычного имени она ставится", () => {
    mount({ kind: "done", next: [PETROV, IVANOV] });
    expect(lines()).toEqual(["Дальше подписывают Петров П. П., Иванов Иван."]);
  });

  it("пока не его очередь: «Сейчас ждём: Петров П. П.» без второй точки", () => {
    mount({ kind: "not_yet", now: [PETROV] });
    expect(lines()).toEqual([
      "Сейчас ждём: Петров П. П.",
      "Когда очередь дойдёт до вас, придёт уведомление.",
    ]);
  });

  it("на английском так же", async () => {
    await i18n.changeLanguage("en");
    mount({ kind: "done", next: [IVANOV, PETROV] });
    expect(lines()).toEqual(["Next to sign: Иванов Иван, Петров П. П."]);
  });
});
