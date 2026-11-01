import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { AccessView } from "./AccessView";

afterEach(cleanup);

const view = (props: Partial<Parameters<typeof AccessView>[0]> = {}) => (
  <I18nextProvider i18n={i18n}>
    <AccessView
      status="ready"
      myRole="owner"
      query="ел"
      onQuery={() => undefined}
      onAdd={() => undefined}
      onChangeRole={() => undefined}
      onRemove={() => undefined}
      {...props}
    />
  </I18nextProvider>
);

describe("AccessView: поиск кандидатов", () => {
  it("сбой поиска не выдаётся за «никого нет» и предлагает повтор", async () => {
    const onRetryCandidates = vi.fn();
    render(view({ candidatesError: true, onRetryCandidates }));
    expect(screen.queryByTestId("access-none")).toBeNull();
    expect(screen.getByTestId("access-search-error")).toBeTruthy();
    await userEvent.click(screen.getByTestId("access-search-retry"));
    expect(onRetryCandidates).toHaveBeenCalledTimes(1);
  });

  it("пустой результат без сбоя показывает «никого нет»", () => {
    render(view());
    expect(screen.getByTestId("access-none")).toBeTruthy();
  });

  it("у выбора роли есть доступное имя", () => {
    render(view());
    expect(screen.getAllByRole("combobox")[0]?.getAttribute("aria-label")).toBe(
      i18n.t("projectAccess:panel.add.role"),
    );
  });
});
