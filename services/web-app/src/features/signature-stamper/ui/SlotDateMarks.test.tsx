import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { DateMarkResponse, PlacementResponse } from "@shared/api/types";
import { SlotDateMarks, type SlotDateMarksProps } from "./SlotDateMarks";

// Метки даты слота в панели размещения (docs/design/signing-route.md, 14.2, 14.11): каждое
// действие сохраняет список меток целиком; у слота вне маршрута ручная дата, у пары маршрута дату
// даёт согласие.

const mark = (overrides: Partial<DateMarkResponse> = {}): DateMarkResponse => ({
  id: "d1",
  page: 1,
  x_mm: 114,
  y_mm: 150,
  width_mm: 7,
  height_mm: 5,
  format: "day",
  align: "center",
  text: null,
  ...overrides,
});

const placement = (
  dates: DateMarkResponse[],
  signedAt: PlacementResponse["signed_at"] = null,
): PlacementResponse => ({
  enabled: true,
  page: 1,
  x_mm: 110,
  y_mm: 130,
  width_mm: 40,
  sign_date: null,
  dates,
  signed_at: signedAt,
});

const mount = (props: Partial<SlotDateMarksProps> = {}) => {
  const onSave = vi.fn();
  const onJumpToPage = vi.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <SlotDateMarks
        slotId="supervisor"
        placement={placement([mark()])}
        lang="ru"
        currentPage={1}
        pageCount={2}
        signatureHeightMm={16}
        signerName="Петров П. П."
        route={null}
        editable
        pending={false}
        onSave={onSave}
        onJumpToPage={onJumpToPage}
        {...props}
      />
    </I18nextProvider>,
  );
  return { onSave, onJumpToPage };
};

const input = (overrides: Partial<DateMarkResponse> = {}) => {
  const { text: _text, ...rest } = mark(overrides);
  return rest;
};

beforeEach(async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-13T09:00:00Z"));
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("метки даты слота", () => {
  it("формат со списком и примером на сегодня, рамка подписана примером", () => {
    mount();
    const select = screen.getByTestId("slot-date-format-supervisor-0");
    const options = within(select)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual([
      "День (13)",
      "Месяц словом (ноября)",
      "Месяц числом (11)",
      "Год (2026)",
      "Год двумя цифрами (26)",
      "Дата (13.11.2026)",
      "Дата словами (13 ноября 2026 г.)",
    ]);
    expect(screen.getByText("Дата: 13")).toBeInTheDocument();
  });

  it("«Добавить дату» ставит новую метку на текущую страницу под подписью", async () => {
    const { onSave } = mount({ currentPage: 2, placement: placement([]) });
    await userEvent.click(screen.getByText("Добавить дату"));
    expect(onSave).toHaveBeenCalledWith({
      dates: [
        {
          id: null,
          page: 2,
          x_mm: 90,
          y_mm: 140,
          width_mm: 28,
          height_mm: 6,
          format: "date_numeric",
          align: "center",
        },
      ],
    });
  });

  it("формат, выравнивание и «Удалить дату» сохраняют список целиком", async () => {
    const { onSave } = mount({
      placement: placement([mark(), mark({ id: "d2", format: "month_word" })]),
    });
    await userEvent.selectOptions(
      screen.getByTestId("slot-date-format-supervisor-0"),
      "date_long",
    );
    expect(onSave).toHaveBeenLastCalledWith({
      dates: [
        input({ format: "date_long" }),
        input({ id: "d2", format: "month_word" }),
      ],
    });
    await userEvent.click(
      within(screen.getByTestId("slot-date-supervisor-1")).getByLabelText(
        "По правому краю",
      ),
    );
    expect(onSave).toHaveBeenLastCalledWith({
      dates: [
        input(),
        input({ id: "d2", format: "month_word", align: "right" }),
      ],
    });
    await userEvent.click(screen.getByTestId("slot-date-remove-supervisor-0"));
    expect(onSave).toHaveBeenLastCalledWith({
      dates: [input({ id: "d2", format: "month_word" })],
    });
  });

  it("метка на другой странице: «Перейти» и «Сюда»", async () => {
    const { onSave, onJumpToPage } = mount({
      placement: placement([mark({ page: 2 })]),
    });
    await userEvent.click(screen.getByText("Перейти"));
    expect(onJumpToPage).toHaveBeenCalledWith(2);
    await userEvent.click(screen.getByText("Сюда"));
    expect(onSave).toHaveBeenCalledWith({ dates: [input({ page: 1 })] });
  });

  it("вне маршрута: «Дата подписи», без неё подсказка; дату можно убрать", () => {
    const { onSave } = mount();
    expect(
      screen.getByText("Без даты метки останутся пустыми"),
    ).toBeInTheDocument();
    const field = screen.getByTestId("slot-date-signed-at-supervisor");
    fireEvent.change(field, { target: { value: "2026-11-10" } });
    expect(onSave).toHaveBeenLastCalledWith({
      dates: [input()],
      signed_at: { date: "2026-11-10" },
    });
    cleanup();
    const second = mount({
      placement: placement([mark({ text: "10" })], {
        at: "2026-11-10",
        source: "manual",
      }),
    });
    expect(screen.getByTestId("slot-date-signed-at-supervisor")).toHaveValue(
      "2026-11-10",
    );
    expect(screen.queryByText("Без даты метки останутся пустыми")).toBeNull();
    fireEvent.change(screen.getByTestId("slot-date-signed-at-supervisor"), {
      target: { value: "" },
    });
    expect(second.onSave).toHaveBeenLastCalledWith({
      dates: [input()],
      signed_at: null,
    });
  });

  it("пара маршрута: ручной даты нет; ждёт подписанта, затем дату даёт согласование", () => {
    mount({ route: { method: "detached" } });
    expect(screen.queryByTestId("slot-date-signed-at-supervisor")).toBeNull();
    expect(
      screen.getByText("Дата появится, когда Петров П. П. подпишет"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Дата подписи добавляет действие подписанту ЭП: согласование до фиксации",
      ),
    ).toBeInTheDocument();
    cleanup();
    mount({
      route: { method: "image" },
      placement: placement([mark({ text: "13" })], {
        at: "2026-11-13T07:30:00+00:00",
        source: "approval",
      }),
    });
    expect(
      screen.getByText("Дату даёт согласование по маршруту"),
    ).toBeInTheDocument();
    expect(screen.getByText("Дата: 13")).toBeInTheDocument();
    expect(screen.queryByText(/добавляет действие подписанту ЭП/)).toBeNull();
  });

  it("предупреждения: текст не помещается, страницы нет в документе", () => {
    mount({
      placement: placement([
        mark({ format: "date_long", width_mm: 10 }),
        mark({ id: "d2", page: 3 }),
      ]),
    });
    expect(screen.getByText("Текст не помещается в рамку")).toBeInTheDocument();
    expect(
      screen.getByText("Страницы 3 нет в документе: дата не попадёт в PDF"),
    ).toBeInTheDocument();
  });

  it("без прав правки: метки видны, кнопок нет", () => {
    mount({ editable: false });
    expect(screen.getByText("Дата: 13")).toBeInTheDocument();
    expect(screen.queryByText("Добавить дату")).toBeNull();
    expect(screen.queryByText("Удалить дату")).toBeNull();
    expect(screen.getByTestId("slot-date-format-supervisor-0")).toBeDisabled();
  });

  it("больше восьми дат не добавить", () => {
    mount({
      placement: placement(
        Array.from({ length: 8 }, (_, i) => mark({ id: `d${String(i + 1)}` })),
      ),
    });
    expect(screen.getByTestId("slot-date-add-supervisor")).toBeDisabled();
  });
});
