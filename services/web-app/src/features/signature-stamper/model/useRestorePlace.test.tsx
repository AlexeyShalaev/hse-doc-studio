import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { signatureApi, signatureKeys } from "@entities/signature";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import type { SignaturesStateResponse } from "@shared/api/types";
import { useRestorePlace } from "./useRestorePlace";

// «Вернуть место из шаблона» (docs/design/signing-route.md, 15.6): документ под маршрутом с ЭП над
// зафиксированным PDF отвечает 409 `resets_signatures`, окно называет сбрасываемые подписи,
// «Вернуть» повторяет запрос с `confirm_reset`, «Отмена» ничего не пишет.

const DOC = "topic_application";
const MOVED = {
  enabled: true,
  page: 1,
  x_mm: 118,
  y_mm: 126,
  width_mm: 40,
  sign_date: null,
  dates: [],
  signed_at: null,
  origin: "manual" as const,
  preset_available: true,
};
const RESTORED = { ...MOVED, x_mm: 110, y_mm: 130, origin: "pack" as const };

const Harness = () => {
  const place = useRestorePlace("p1");
  return (
    <>
      <button
        type="button"
        onClick={() => {
          place.restore(DOC, "supervisor");
        }}
      >
        restore
      </button>
      {place.dialog}
    </>
  );
};

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const state: SignaturesStateResponse = {
    slots: {},
    placements: { [DOC]: { supervisor: MOVED } },
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

describe("«Вернуть место из шаблона»", () => {
  it("ответ встаёт в состояние подписей", async () => {
    const post = vi
      .spyOn(signatureApi, "restorePlacement")
      .mockResolvedValue(RESTORED);
    const client = mount();
    await userEvent.click(screen.getByText("restore"));
    expect(post).toHaveBeenCalledWith("p1", DOC, "supervisor", {
      confirm_reset: false,
    });
    await waitFor(() => {
      expect(
        client.getQueryData<SignaturesStateResponse>(signatureKeys.state("p1"))
          ?.placements[DOC]?.supervisor?.origin,
      ).toBe("pack");
    });
  });

  it("409 resets_signatures: окно называет подписи, «Вернуть» повторяет с confirm_reset", async () => {
    const post = vi
      .spyOn(signatureApi, "restorePlacement")
      .mockRejectedValueOnce(
        new ApiError("Restoring resets signatures", "resets_signatures", 409, {
          resets: [
            { doc_id: DOC, slot_id: "supervisor", name: "Петров П. П." },
          ],
        }),
      )
      .mockResolvedValueOnce(RESTORED);
    mount();
    await userEvent.click(screen.getByText("restore"));
    expect(await screen.findByTestId("dates-reset-text")).toHaveTextContent(
      "Подписи будут сброшены: Петров П. П. Документ зафиксируют заново, и они подпишут итоговый PDF ещё раз. Вернуть?",
    );
    expect(screen.getByText("Вернуть место из шаблона?")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("dates-reset-confirm"));
    await waitFor(() => {
      expect(post).toHaveBeenCalledTimes(2);
    });
    expect(post).toHaveBeenLastCalledWith("p1", DOC, "supervisor", {
      confirm_reset: true,
    });
    await waitFor(() => {
      expect(screen.queryByTestId("dates-reset-text")).toBeNull();
    });
  });

  it("«Отмена» закрывает окно без повторного запроса", async () => {
    const post = vi
      .spyOn(signatureApi, "restorePlacement")
      .mockRejectedValueOnce(
        new ApiError("Restoring resets signatures", "resets_signatures", 409, {
          resets: [],
        }),
      );
    mount();
    await userEvent.click(screen.getByText("restore"));
    await screen.findByTestId("dates-reset-text");
    await userEvent.click(screen.getByText("Отмена"));
    expect(screen.queryByTestId("dates-reset-text")).toBeNull();
    expect(post).toHaveBeenCalledTimes(1);
  });
});
