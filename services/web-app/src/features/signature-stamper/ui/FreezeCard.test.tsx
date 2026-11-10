import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { FreezeCard } from "./DetachedSignatureBlocks";

// «Файл на подпись» документа, который держит идущий маршрут (docs/design/signing-route.md, 6.10):
// фиксирует только маршрут, поэтому вместо «пересобран, зафиксируйте заново» сказано, что PDF
// зафиксирует маршрут, а кнопок фиксации и её снятия нет (сервер ответил бы 409 route_locked).

const STALE = {
  sha256: "5409b0b3",
  size: 104_000,
  frozen_at: "2026-11-09T15:09:00Z",
  stale: true,
  plate_outdated: false,
};

const mount = (routeHeld: boolean, frozen: typeof STALE | null = STALE) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>
        <FreezeCard
          projectId="p1"
          docId="topic_application"
          frozen={frozen ?? undefined}
          signatureCount={1}
          pdfAvailable
          routeHeld={routeHeld}
        />
      </QueryClientProvider>
    </I18nextProvider>,
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
});

describe("Файл на подпись и маршрут подписания", () => {
  it("документ на маршруте: PDF зафиксирует маршрут, кнопок фиксации нет", () => {
    mount(true);
    expect(screen.getByTestId("freeze-by-route")).toHaveTextContent(
      "PDF зафиксирует маршрут, когда все согласуют.",
    );
    expect(screen.queryByText(/Документ пересобран после фиксации/)).toBeNull();
    expect(screen.queryByText("Зафиксировать заново")).toBeNull();
    expect(screen.queryByText("Снять фиксацию")).toBeNull();
    // Скачать то, что зафиксировано раньше, можно и сейчас.
    expect(screen.getByText("Скачать PDF")).toBeInTheDocument();
  });

  it("на маршруте и без фиксации: кнопки «Зафиксировать» нет", () => {
    mount(true, null);
    expect(screen.getByTestId("freeze-by-route")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("без маршрута: предупреждение и кнопки как прежде", () => {
    mount(false);
    expect(screen.queryByTestId("freeze-by-route")).toBeNull();
    expect(
      screen.getByText(/Документ пересобран после фиксации/),
    ).toBeInTheDocument();
    expect(screen.getByText("Зафиксировать заново")).toBeInTheDocument();
    expect(screen.getByText("Снять фиксацию")).toBeInTheDocument();
  });
});
