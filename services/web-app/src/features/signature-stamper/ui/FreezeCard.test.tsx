import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import type { DetachedSignatureResponse } from "@shared/api/types";
import { FreezeCard, SlotDetachedSignature } from "./DetachedSignatureBlocks";

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

// Старая ручная подпись автора (09.11, до маршрута) к прежней фиксации: на маршруте это не ошибка.
const OLD_SIGNATURE: DetachedSignatureResponse = {
  format: "openpgp",
  origin: "studio",
  verdict: "valid",
  signer: "Алексей Шалаев",
  signer_id: "A69C068EDAA6150C",
  issuer: "",
  algorithm: "",
  signed_at: "2026-11-09T15:09:00Z",
  not_before: null,
  not_after: null,
  chain: null,
  root_subject: "",
  root_fingerprint: "",
  notes: [],
  added_at: "2026-11-09T15:09:00Z",
  file_name: "author.asc",
  current: false,
};

const mountSlot = (
  routeHeld: boolean,
  frozen: typeof STALE = STALE,
  signature: DetachedSignatureResponse = OLD_SIGNATURE,
) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>
        <SlotDetachedSignature
          projectId="p1"
          docId="topic_application"
          slotId="author"
          label="Автор работы"
          personName="Алексей Шалаев"
          frozen={frozen}
          signature={signature}
          routeHeld={routeHeld}
        />
      </QueryClientProvider>
    </I18nextProvider>,
  );

describe("Подпись слота и маршрут подписания", () => {
  it("на маршруте: подпись к прежнему PDF спокойно, без проверки и удаления", () => {
    mountSlot(true);
    expect(
      screen.getByText(
        "Подпись к прежней версии PDF. Маршрут попросит подписать заново после фиксации.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Недействительна/)).toBeNull();
    expect(screen.queryByTitle("Проверить снова")).toBeNull();
    expect(screen.queryByTitle("Удалить подпись")).toBeNull();
    // Скачать старый файл подписи можно.
    expect(screen.getByTitle("Скачать файл подписи")).toBeInTheDocument();
  });

  it("на маршруте после новой фиксации: подписать заново попросит маршрут", () => {
    mountSlot(true, { ...STALE, stale: false });
    expect(
      screen.getByText(
        "Подпись к прежней версии PDF. Маршрут попросит подписать заново.",
      ),
    ).toBeInTheDocument();
  });

  it("на маршруте действующая подпись: проверить можно, удалить нельзя", () => {
    mountSlot(
      true,
      { ...STALE, stale: false },
      { ...OLD_SIGNATURE, current: true },
    );
    expect(screen.getByText("Подпись верна")).toBeInTheDocument();
    expect(screen.getByTitle("Проверить снова")).toBeInTheDocument();
    expect(screen.queryByTitle("Удалить подпись")).toBeNull();
  });

  it("без маршрута: красное «недействительна» и действия как прежде", () => {
    mountSlot(false);
    expect(
      screen.getByText("Недействительна: PDF пересобран"),
    ).toBeInTheDocument();
    expect(screen.getByTitle("Проверить снова")).toBeInTheDocument();
    expect(screen.getByTitle("Удалить подпись")).toBeInTheDocument();
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    mountSlot(true);
    expect(
      screen.getByText(
        "Signature for an earlier PDF version. The route will ask to sign again after the freeze.",
      ),
    ).toBeInTheDocument();
  });
});
