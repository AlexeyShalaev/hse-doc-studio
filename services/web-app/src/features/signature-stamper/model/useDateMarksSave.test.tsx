import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { signatureApi, signatureKeys } from "@entities/signature";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type { SignaturesStateResponse } from "@shared/api/types";
import { useDateMarksSave } from "./useDateMarksSave";

// Сохранение меток даты на документе под маршрутом (docs/design/signing-route.md, 14.6): сервер
// отвечает 409 `resets_signatures`, окно называет сбрасываемые подписи, «Сохранить» повторяет
// запрос с `confirm_reset`, «Отмена» ничего не пишет.

const DOC = "topic_application";
const MARK = {
  id: "d1",
  page: 1,
  x_mm: 114,
  y_mm: 150,
  width_mm: 7,
  height_mm: 5,
  format: "day" as const,
  align: "center" as const,
};
const PLACEMENT = {
  enabled: true,
  page: 1,
  x_mm: 110,
  y_mm: 130,
  width_mm: 40,
  sign_date: null,
  dates: [{ ...MARK, text: "13" }],
  signed_at: { at: "2026-11-13T07:30:00+00:00", source: "approval" as const },
  origin: "manual" as const,
  preset_available: true,
  source: null,
  anchor: null,
};

const Harness = () => {
  const saver = useDateMarksSave("p1");
  return (
    <>
      <button
        type="button"
        onClick={() => {
          saver.save(DOC, "supervisor", { dates: [MARK] });
        }}
      >
        save
      </button>
      <button
        type="button"
        onClick={() => {
          saver.movePlace(DOC, "supervisor", PLACEMENT, 0, {
            x_mm: 120.123,
            y_mm: 151,
            width_mm: 8,
            height_mm: 5,
          });
        }}
      >
        move
      </button>
      {saver.dialog}
    </>
  );
};

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const state: SignaturesStateResponse = {
    slots: {},
    placements: { [DOC]: { supervisor: PLACEMENT } },
  };
  client.setQueryData(signatureKeys.state("p1"), state);
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>
    </I18nextProvider>,
  );
  return client;
};

const resets = () =>
  new ApiError("Saving resets signatures", "resets_signatures", 409, {
    resets: [
      { doc_id: DOC, slot_id: "supervisor", name: "Петров П. П." },
      { doc_id: DOC, slot_id: "academic_supervisor", name: "Сидоров С. С." },
    ],
  });

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  vi.spyOn(signatureApi, "getState").mockReturnValue(
    new Promise(() => undefined),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("сохранение меток даты", () => {
  it("409 resets_signatures: окно называет подписи, «Сохранить» повторяет с confirm_reset", async () => {
    const put = vi
      .spyOn(signatureApi, "setDateMarks")
      .mockRejectedValueOnce(resets())
      .mockResolvedValueOnce(PLACEMENT);
    mount();
    await userEvent.click(screen.getByText("save"));
    expect(await screen.findByTestId("dates-reset-text")).toHaveTextContent(
      "Подписи будут сброшены: Петров П. П., Сидоров С. С. Документ зафиксируют заново, и они подпишут итоговый PDF ещё раз. Сохранить?",
    );
    expect(put).toHaveBeenLastCalledWith("p1", DOC, "supervisor", {
      dates: [MARK],
      confirm_reset: false,
    });
    await userEvent.click(screen.getByTestId("dates-reset-confirm"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(2);
    });
    expect(put).toHaveBeenLastCalledWith("p1", DOC, "supervisor", {
      dates: [MARK],
      confirm_reset: true,
    });
    await waitFor(() => {
      expect(screen.queryByTestId("dates-reset-text")).toBeNull();
    });
  });

  it("«Отмена» закрывает окно без повторного запроса", async () => {
    const put = vi
      .spyOn(signatureApi, "setDateMarks")
      .mockRejectedValueOnce(resets());
    mount();
    await userEvent.click(screen.getByText("save"));
    await screen.findByTestId("dates-reset-text");
    await userEvent.click(screen.getByText("Отмена"));
    expect(screen.queryByTestId("dates-reset-text")).toBeNull();
    expect(put).toHaveBeenCalledTimes(1);
  });

  it("перетаскивание: место до сотых, остальные поля метки как были; кэш сразу с новым местом", async () => {
    const put = vi
      .spyOn(signatureApi, "setDateMarks")
      .mockReturnValue(new Promise(() => undefined));
    const client = mount();
    await userEvent.click(screen.getByText("move"));
    expect(put).toHaveBeenCalledWith("p1", DOC, "supervisor", {
      dates: [{ ...MARK, x_mm: 120.12, y_mm: 151, width_mm: 8 }],
      confirm_reset: false,
    });
    const state = client.getQueryData<SignaturesStateResponse>(
      signatureKeys.state("p1"),
    );
    expect(state?.placements[DOC]?.supervisor?.dates).toEqual([
      { ...MARK, x_mm: 120.12, y_mm: 151, width_mm: 8, text: "13" },
    ]);
  });
});
