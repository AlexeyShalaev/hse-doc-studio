import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { whenChoice, whenValue, siblingFields } from "../../lib/ruleRecord";
import type { RuleChange, RuleFormContext, RuleShape } from "../../rule";
import { RuleRecordForm } from "./RuleRecordForm";

const MANIFEST = {
  langs: ["ru", "en"],
  forms: [
    {
      sections: [
        {
          fields: [
            { id: "used_ai" },
            { id: "tools", visible_if: { field: "used_ai", equals: true } },
            { id: "other" },
          ],
        },
      ],
    },
  ],
};
const CONTEXT: RuleFormContext = {
  manifest: MANIFEST,
  checkRules: ["a_rule", "b_rule"],
  checkCategories: ["gost"],
};

const setup = (
  shape: RuleShape,
  pointer: string,
  value: unknown,
  disabled = false,
) => {
  const onChange = vi.fn<(change: RuleChange) => void>();
  render(
    <RuleRecordForm
      shape={shape}
      pointer={pointer}
      value={value}
      context={CONTEXT}
      disabled={disabled}
      onChange={onChange}
      testId="rule-form"
    />,
  );
  return onChange;
};

describe("мини-форма записи манифеста", () => {
  beforeAll(async () => {
    await loadPackFormsNamespace();
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("запись помечена указателем для привязки формы", () => {
    setup({ kind: "list", list: "kinds" }, "/supported_kinds", undefined);
    expect(screen.getByTestId("rule-form")).toHaveAttribute(
      "data-pf-at",
      "/supported_kinds",
    );
  });

  describe("список значений", () => {
    it("нет ключа: всё отмечено; снять одно пишет оставшееся", async () => {
      const onChange = setup(
        { kind: "list", list: "kinds" },
        "/supported_kinds",
        undefined,
      );
      const project = screen.getByRole("checkbox", { name: "Проектная" });
      expect(project).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: "Исследовательская" }),
      ).toBeChecked();
      await userEvent.click(project);
      expect(onChange).toHaveBeenCalledWith({
        type: "set",
        value: ["research"],
      });
    });

    it("отмечено всё или ничего: ключ убирается (ограничения нет)", async () => {
      const onChange = setup(
        { kind: "list", list: "kinds" },
        "/supported_kinds",
        ["research"],
      );
      await userEvent.click(
        screen.getByRole("checkbox", { name: "Проектная" }),
      );
      expect(onChange).toHaveBeenCalledWith({ type: "remove" });
    });

    it("состав и языки версии", async () => {
      cleanup();
      setup({ kind: "list", list: "staffing" }, "/supported_staffing", [
        "solo",
      ]);
      expect(
        screen.getByRole("checkbox", { name: "Один автор" }),
      ).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: "Команда" }),
      ).not.toBeChecked();
      cleanup();
      setup({ kind: "list", list: "langs" }, "/supported_langs", ["ru"]);
      expect(
        screen.getByRole("checkbox", { name: "Английский" }),
      ).not.toBeChecked();
    });

    it("недоступная форма отключает поля", () => {
      setup(
        { kind: "list", list: "kinds" },
        "/supported_kinds",
        undefined,
        true,
      );
      expect(
        screen.getByRole("checkbox", { name: "Проектная" }),
      ).toBeDisabled();
    });
  });

  describe("галочки", () => {
    it("NDA: поставить пишет true, снять убирает ключ", async () => {
      const onChange = setup(
        { kind: "flag", flag: "skip_if_nda" },
        "/pack_submission/profiles/0/items/0/skip_if_nda",
        undefined,
      );
      await userEvent.click(
        screen.getByRole("checkbox", { name: /Пропускать пункт при NDA/ }),
      );
      expect(onChange).toHaveBeenCalledWith({ type: "set", value: true });
      cleanup();
      const off = setup(
        { kind: "flag", flag: "optional" },
        "/pack_submission/profiles/0/signing_slots/0/optional",
        true,
      );
      await userEvent.click(
        screen.getByRole("checkbox", { name: /Подпись необязательна/ }),
      );
      expect(off).toHaveBeenCalledWith({ type: "remove" });
    });
  });

  describe("условие показа поля", () => {
    const POINTER = "/forms/0/sections/0/fields/1/visible_if";
    it("поля той же анкеты, кроме самого поля; значение пишется скаляром", () => {
      expect(siblingFields(MANIFEST, POINTER)).toEqual(["used_ai", "other"]);
    });

    it("выбор поля, значение и «Всегда»", async () => {
      const onChange = setup({ kind: "visibleIf" }, POINTER, {
        field: "used_ai",
        equals: true,
      });
      const select = screen.getByRole("combobox", {
        name: "Показывать, когда",
      });
      expect(select).toHaveValue("used_ai");
      const equals = screen.getByRole("textbox", { name: "Значение" });
      expect(equals).toHaveValue("true");
      await userEvent.clear(equals);
      await userEvent.type(equals, "no{Enter}");
      expect(onChange).toHaveBeenLastCalledWith({
        type: "set",
        value: { field: "used_ai", equals: "no" },
      });
      await userEvent.selectOptions(select, "");
      expect(onChange).toHaveBeenLastCalledWith({ type: "remove" });
      await userEvent.selectOptions(select, "other");
      expect(onChange).toHaveBeenLastCalledWith({
        type: "set",
        value: { field: "other", equals: true },
      });
    });

    it("«true» и «false» пишутся логическими значениями", async () => {
      const onChange = setup({ kind: "visibleIf" }, POINTER, {
        field: "used_ai",
        equals: "x",
      });
      const equals = screen.getByRole("textbox", { name: "Значение" });
      fireEvent.change(equals, { target: { value: "false" } });
      fireEvent.blur(equals);
      expect(onChange).toHaveBeenCalledWith({
        type: "set",
        value: { field: "used_ai", equals: false },
      });
    });
  });

  describe("условие слота подписи", () => {
    const POINTER = "/pack_submission/profiles/0/signing_slots/1/when";
    it("закрытый список: всегда, человек, человек с ролью", async () => {
      const onChange = setup({ kind: "when" }, POINTER, {
        person: "supervisor",
        role: "company",
      });
      const select = screen.getByRole("combobox", { name: "Условие слота" });
      expect(select).toHaveValue("supervisor:company");
      expect(select).toHaveDisplayValue(
        "если научный руководитель указан и из компании",
      );
      await userEvent.selectOptions(select, "always");
      expect(onChange).toHaveBeenLastCalledWith({ type: "remove" });
      await userEvent.selectOptions(select, "academic_supervisor:university");
      expect(onChange).toHaveBeenLastCalledWith({
        type: "set",
        value: { person: "academic_supervisor", role: "university" },
      });
      await userEvent.selectOptions(select, "co_supervisor");
      expect(onChange).toHaveBeenLastCalledWith({
        type: "set",
        value: { person: "co_supervisor" },
      });
    });

    it("нет ключа это «всегда»; выбор и значение взаимно обратимы", () => {
      setup({ kind: "when" }, POINTER, undefined);
      expect(
        screen.getByRole("combobox", { name: "Условие слота" }),
      ).toHaveValue("always");
      expect(whenChoice({ person: "supervisor" })).toBe("supervisor");
      expect(whenValue("supervisor:company")).toEqual({
        type: "set",
        value: { person: "supervisor", role: "company" },
      });
    });
  });

  describe("проверки версии", () => {
    it("отключённые правила: набор из правил версии и уже записанных", async () => {
      const onChange = setup(
        { kind: "checks", list: "disabled" },
        "/checks_version/disabled",
        ["old_rule"],
      );
      expect(screen.getByRole("checkbox", { name: "old_rule" })).toBeChecked();
      expect(
        screen.getByRole("checkbox", { name: "a_rule" }),
      ).not.toBeChecked();
      await userEvent.click(screen.getByRole("checkbox", { name: "a_rule" }));
      expect(onChange).toHaveBeenCalledWith({
        type: "set",
        value: ["a_rule", "old_rule"],
      });
    });
  });

  it("порядок подписания: только подсказка, полей нет", () => {
    setup(
      { kind: "route" },
      "/pack_submission/profiles/0/signing_route",
      undefined,
    );
    expect(screen.getByTestId("rule-form")).toHaveTextContent(
      "Порядок подписания правится целиком",
    );
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("английские подписи", async () => {
    await i18n.changeLanguage("en");
    try {
      setup({ kind: "when" }, "/x/when", { person: "co_supervisor" });
      expect(
        screen.getByRole("combobox", { name: "Slot condition" }),
      ).toHaveDisplayValue("if the consultant is set");
    } finally {
      await i18n.changeLanguage("ru");
    }
  });
});
