import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { OutcomeCoverage } from "@entities/pack-studio";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { CoverageBlock } from "./CoverageBlock";
import { LintActionsContext, type LintActions } from "./context";

// Блок «Покрытие» отдельно от экрана: пограничные ответы сервера (приближённое покрытие, лимит
// правил, ни одного сценария, зашитые правила, ответ без необязательных полей).

const actions = (over: Partial<LintActions> = {}): LintActions => ({
  labeler: { input: (id) => id, value: (_id, value) => value },
  showCombination: vi.fn(),
  showElement: vi.fn(),
  openPlace: vi.fn(() => true),
  openRule: vi.fn(() => true),
  addScenario: vi.fn(),
  canAddScenario: true,
  ...over,
});

const ruleOf = (n: number, seen: ("held" | "not_held")[] = []) => ({
  rule: {
    origin: "manifest" as const,
    file: "version.yaml",
    pointer: `/r/${String(n)}`,
    builtin: null,
  },
  kind: "visible_if" as const,
  seen,
  possible: ["held", "not_held"] as ("held" | "not_held")[],
  scenarios: seen.length > 0 ? ["one"] : [],
  witness: { supervisor: "none" },
});

const base: OutcomeCoverage = {
  scenarios: 1,
  rules_total: 30,
  rules_covered: 18,
  rules_half: 9,
  rules_uncovered: 3,
  rules: [],
};

const draw = (coverage: OutcomeCoverage, over: Partial<LintActions> = {}) => {
  const value = actions(over);
  render(
    <LintActionsContext.Provider value={value}>
      <CoverageBlock coverage={coverage} />
    </LintActionsContext.Provider>,
  );
  return value;
};

describe("блок «Покрытие» (F11)", () => {
  beforeAll(async () => {
    await loadPackOutcomeNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("лимит правил: восемь сразу, остальные по кнопке, rules_omitted пишет о скрытых", async () => {
    const user = userEvent.setup();
    draw({
      ...base,
      percent: 55,
      rules: Array.from({ length: 12 }, (_, n) => ruleOf(n, ["held"])),
      rules_omitted: 3,
    });
    expect(screen.getAllByTestId("outcome-lint-coverage-rule")).toHaveLength(8);
    await user.click(screen.getByTestId("outcome-lint-rules-all"));
    expect(screen.getAllByTestId("outcome-lint-coverage-rule")).toHaveLength(
      12,
    );
    expect(screen.queryByTestId("outcome-lint-rules-all")).toBeNull();
    expect(screen.getByTestId("outcome-lint-omitted")).toHaveTextContent(
      "Ещё 3 правила не показаны.",
    );
  });

  it("ни одного сценария: «Добавить сценарий» открывает окно сразу", async () => {
    const user = userEvent.setup();
    const value = draw({ ...base, scenarios: 0, percent: 0 });
    expect(screen.getByTestId("outcome-lint-percent")).toHaveTextContent("0 %");
    const add = screen.getByTestId("outcome-lint-add-scenarios");
    expect(add).toHaveTextContent("Добавить сценарий");
    await user.click(add);
    expect(value.addScenario).toHaveBeenCalledWith(null);
  });

  it("зашитое правило: подпись движка, «Открыть правило» нет; свидетель показывает комбинацию", async () => {
    const user = userEvent.setup();
    const value = draw({
      ...base,
      percent: 70,
      rules: [
        {
          ...ruleOf(1, ["not_held"]),
          rule: {
            origin: "builtin",
            file: null,
            pointer: null,
            builtin: "nda_gate",
          },
          kind: "builtin_gate",
        },
      ],
    });
    const item = screen.getByTestId("outcome-lint-coverage-rule");
    expect(item).toHaveTextContent("Правило движка");
    expect(item).toHaveTextContent("Сценарии видели: не выполнено.");
    expect(item).toHaveTextContent("Не хватает: выполнено.");
    expect(
      within(item).queryByTestId("outcome-lint-open-coverage-rule"),
    ).toBeNull();
    await user.click(within(item).getByTestId("outcome-lint-show-combo"));
    expect(value.showCombination).toHaveBeenCalledWith({ supervisor: "none" });
  });

  it("ответ без необязательных полей: процент по числам, строк атласа и подсказок нет", () => {
    draw({ ...base, rules_covered: 15, rules_half: 15, rules_uncovered: 0 });
    expect(screen.getByTestId("outcome-lint-percent")).toHaveTextContent(
      "50 %",
    );
    expect(screen.queryByTestId("outcome-lint-suggest")).toBeNull();
    expect(screen.queryByTestId("outcome-lint-approximate")).toBeNull();
    expect(screen.queryByText(/Строк атласа затронуто/)).toBeNull();
  });

  it("запись сценариев запрещена: кнопка отключена, окно не открывается", async () => {
    const user = userEvent.setup();
    const value = draw(
      {
        ...base,
        percent: 40,
        uncovered_rows: [{ inputs: { supervisor: "none" }, gain: 1 }],
      },
      { canAddScenario: false },
    );
    const add = screen.getByTestId("outcome-lint-add-scenarios");
    expect(add).toBeDisabled();
    await user.click(add);
    expect(value.addScenario).not.toHaveBeenCalled();
  });

  it("приближённое покрытие помечено в потоке статусов", () => {
    draw({ ...base, percent: 20, approximate: true });
    expect(screen.getByTestId("outcome-lint-approximate")).toHaveAttribute(
      "role",
      "status",
    );
  });
});
