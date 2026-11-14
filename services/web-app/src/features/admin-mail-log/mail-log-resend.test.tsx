import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { mailLogApi } from "./api/mailLogApi";
import { resendBatchBodyOf } from "./api/mailLogQueries";
import type { MailLogDetail } from "./api/schemas";
import { ensureAdminMailLocales } from "./lib/locales";
import { mailNextSteps } from "./lib/mailLog";
import {
  MAIL_LOG_DETAILS,
  MAIL_LOG_RECORDS,
  MAIL_LOG_SUMMARIES,
  MAIL_NOW,
} from "./testing";
import { MailLog } from "./ui/MailLog";
import { MailDayBand } from "./ui/MailLogView";
import { MailLogCardView, type MailResendNotice } from "./ui/MailLogCardView";
import { getAdminMailLogGallery } from "./ui/mailLogGallery";

// Журнал писем v2 (docs/design/mail-log.md, раздел 14): автоповтор в списке и карточке,
// «Отправить ещё раз», «Отправить неушедшие» и их ответы на демо-мире.

const NOW = Date.parse(MAIL_NOW);
const noop = () => undefined;

const LocationProbe = () => {
  const loc = useLocation();
  return (
    <span hidden data-testid="where">
      {`${loc.pathname}${loc.search}`}
    </span>
  );
};
const where = (): string => screen.getByTestId("where").textContent;

const wrap = (node: ReactNode, url = "/admin/mail") => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[url]}>
        {node}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const card = (
  detail: MailLogDetail,
  options: { onResend?: () => void; notice?: MailResendNotice } = {},
) =>
  render(
    wrap(
      <MailLogCardView
        entry={detail.entry}
        detail={detail}
        state="ready"
        now={NOW}
        onRetry={noop}
        onClose={noop}
        onShowRecipient={noop}
        onShowProject={noop}
        onResend={options.onResend ?? noop}
        resendNotice={options.notice ?? null}
      />,
    ),
  );

const D = MAIL_LOG_DETAILS;

beforeAll(async () => {
  installServerDemo();
  await ensureAdminMailLocales();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  activateServerScenario("admin_ready");
});
afterEach(cleanup);

describe("что можно сделать: повтор", () => {
  it("ждёт автоповтора: делать ничего не нужно; неактуально: причина", () => {
    const kinds = (blocked: string | null, next: string | null = null) =>
      mailNextSteps(
        {
          template: "signing_request",
          status: "failed",
          reason: "recipient_refused",
          next_attempt_at: next,
        },
        blocked,
      ).map((s) => (s.kind === "stale" ? `stale:${s.code}` : s.kind));

    expect(kinds("retrying", MAIL_NOW)).toEqual(["retrying", "template"]);
    expect(kinds("route_done")).toEqual(["stale:route_done", "template"]);
    // Токен и тестовое письмо объясняют подсказки по виду, итог `sent` объяснять не нужно.
    expect(kinds("token_link")).toEqual(["template"]);
    expect(kinds("status")).toEqual(["template"]);
    expect(kinds(null)).toEqual(["template"]);
  });
});

describe("карточка: автоповтор и повтор", () => {
  it("ждёт автоповтора: метка «Повтор», время попытки, кнопки нет", () => {
    card(D.retrying);
    expect(screen.getByTestId("mail-card-badge")).toHaveTextContent("Повтор");
    expect(screen.getByTestId("mail-card-retry")).toHaveTextContent(
      /Студия повторит отправку в \d{2}:\d{2}\. Попытка 3 из 5\./,
    );
    expect(screen.getByTestId("mail-card-attempts")).toHaveTextContent(
      "2 из 5",
    );
    expect(screen.getByTestId("mail-card-last-attempt")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-card-resend")).toBeNull();
    expect(
      within(screen.getByTestId("mail-card-next")).getByText(
        "Ничего делать не нужно: Студия сама повторит отправку.",
      ),
    ).toBeInTheDocument();
  });

  it("попытки кончились: «Отправить ещё раз» зовёт обработчик", async () => {
    const user = userEvent.setup();
    let calls = 0;
    card(D.resend_allowed, {
      onResend: () => {
        calls += 1;
      },
    });
    expect(screen.getByTestId("mail-card-retry")).toHaveTextContent(
      "Студия пробовала 5 раз, письмо так и не ушло.",
    );
    await user.click(screen.getByTestId("mail-card-resend"));
    expect(calls).toBe(1);
  });

  it("неактуально: кнопки нет, причина в «Что можно сделать»", () => {
    card(D.stale_route);
    expect(screen.queryByTestId("mail-card-resend")).toBeNull();
    expect(screen.getByTestId("mail-card-next")).toHaveTextContent(
      "Отправлять ещё раз не нужно: маршрут уже подписан или остановлен",
    );
  });

  it("повторено: список повторов и плашка итога; у копии ссылка на исходное", () => {
    card(D.resent, {
      notice: { tone: "info", text: "Письмо отправлено ещё раз." },
    });
    expect(screen.getByTestId("mail-card-resend-notice")).toHaveTextContent(
      "Письмо отправлено ещё раз.",
    );
    expect(screen.getByTestId("mail-card-resent")).toHaveTextContent(
      "отправлено",
    );
    expect(screen.getByTestId("mail-card-next")).toHaveTextContent(
      "письмо уже отправлено ещё раз и ушло",
    );
    cleanup();
    card(D.resent_copy);
    expect(screen.getByTestId("mail-card-resent-from")).toHaveTextContent(
      `№ ${String(MAIL_LOG_RECORDS.gave_up.entry.id)}`,
    );
    expect(screen.getByTestId("mail-card-origin")).toHaveTextContent(
      "Повтор из журнала",
    );
  });

  it("письмо с токеном не повторяется: кнопки нет", () => {
    card(D.failed_with_note);
    expect(screen.queryByTestId("mail-card-resend")).toBeNull();
  });
});

describe("полоса за сутки", () => {
  it("«Ждут повтора» видно, только когда они есть, и ставит фильтр", async () => {
    const user = userEvent.setup();
    let clicks = 0;
    render(
      wrap(
        <MailDayBand
          summary={MAIL_LOG_SUMMARIES.normal}
          onFailed={noop}
          onRetrying={() => {
            clicks += 1;
          }}
        />,
      ),
    );
    await user.click(screen.getByTestId("mail-day-retrying"));
    expect(clicks).toBe(1);
    expect(screen.getByTestId("mail-day-retrying")).toHaveTextContent(
      "Ждут повтора 2",
    );
    cleanup();
    render(
      wrap(<MailDayBand summary={MAIL_LOG_SUMMARIES.quiet} onFailed={noop} />),
    );
    expect(screen.queryByTestId("mail-day-retrying")).toBeNull();
  });
});

describe("API повтора на демо-мире", () => {
  it("повтор одного письма: новая строка со ссылкой на исходную, второй раз не нужно", async () => {
    const id = MAIL_LOG_RECORDS.gave_up.entry.id;
    const first = await mailLogApi.resend(id);
    expect(first.outcome).toBe("sent");
    expect(first.entry_id).not.toBeNull();
    const copy = await mailLogApi.entry(first.entry_id ?? 0);
    expect(copy.entry.resent_from_id).toBe(id);
    expect(copy.entry.origin).toBe("admin_resend");
    const original = await mailLogApi.entry(id);
    expect(original.resend).toEqual({
      allowed: false,
      blocked: "already_resent",
    });
    expect(original.resent.map((r) => r.id)).toEqual([first.entry_id]);
    expect(await mailLogApi.resend(id)).toMatchObject({
      outcome: "blocked",
      blocked: "already_resent",
    });
    expect(
      await mailLogApi.resend(MAIL_LOG_RECORDS.token_link.entry.id),
    ).toMatchObject({ outcome: "blocked", blocked: "status" });
  });

  it("«Отправить неушедшие»: предпросмотр не шлёт, запуск шлёт", async () => {
    const preview = await mailLogApi.resendBatch(
      resendBatchBodyOf({ limit: 50 }, true),
    );
    expect(preview.started).toBe(false);
    expect(preview.planned).toBeGreaterThan(0);
    expect(preview.skipped.token_link).toBeGreaterThan(0);
    const started = await mailLogApi.resendBatch(
      resendBatchBodyOf({ limit: 50 }, false),
    );
    expect(started).toMatchObject({ started: true, planned: preview.planned });
    const again = await mailLogApi.resendBatch(
      resendBatchBodyOf({ limit: 50 }, true),
    );
    expect(again.planned).toBe(0);
  });

  it("тело пачки из параметров списка: период как since и until", () => {
    expect(
      resendBatchBodyOf(
        {
          limit: 50,
          template: ["signing_request"],
          status: ["failed"],
          from: "2026-11-10T00:00:00.000Z",
          q: "anna",
        },
        true,
      ),
    ).toEqual({
      template: ["signing_request"],
      reason: null,
      recipient_id: null,
      recipient: null,
      project_id: null,
      since: "2026-11-10T00:00:00.000Z",
      until: null,
      q: "anna",
      dry_run: true,
    });
  });
});

describe("раздел на демо-мире", () => {
  it("«Отправить ещё раз» в карточке: плашка и новая строка в повторах", async () => {
    const user = userEvent.setup();
    const id = MAIL_LOG_RECORDS.gave_up.entry.id;
    render(wrap(<MailLog />, `/admin/mail?mail=${String(id)}`));
    const cardEl = await screen.findByTestId("mail-card");
    await user.click(await within(cardEl).findByTestId("mail-card-resend"));
    expect(
      await within(cardEl).findByTestId("mail-card-resend-notice"),
    ).toHaveTextContent("Письмо отправлено ещё раз.");
    expect(
      await within(cardEl).findByTestId("mail-card-resent"),
    ).toBeInTheDocument();
    await user.click(
      within(cardEl).getByRole("button", { name: /отправлено/ }),
    );
    await waitFor(() => {
      expect(where()).not.toContain(`mail=${String(id)}`);
    });
  }, 20_000);

  it("«Отправить неушедшие»: окно с предпросмотром и запуск", async () => {
    const user = userEvent.setup();
    render(wrap(<MailLog />));
    await user.click(await screen.findByTestId("mail-resend-batch"));
    expect(await screen.findByTestId("mail-batch-planned")).toHaveTextContent(
      /Будет отправлено писем: \d+\./,
    );
    expect(screen.getByTestId("mail-batch-skipped")).toHaveTextContent(
      "в письме была ссылка с токеном",
    );
    await user.click(screen.getByTestId("mail-batch-submit"));
    await waitFor(() => {
      expect(screen.queryByTestId("mail-batch")).toBeNull();
    });
  }, 20_000);

  it("без SMTP кнопки «Отправить неушедшие» нет", async () => {
    activateServerScenario("admin_sso");
    render(wrap(<MailLog />));
    expect(await screen.findByTestId("mail-smtp-off")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-resend-batch")).toBeNull();
  }, 20_000);

  it("«Ждут повтора» из адреса уходит на сервер", async () => {
    render(wrap(<MailLog />, "/admin/mail?retrying=true"));
    const table = await screen.findByRole("table", { name: "Журнал писем" });
    await waitFor(() => {
      expect(within(table).getAllByTestId(/^mail-status-/)).toHaveLength(1);
    });
    expect(within(table).getByTestId(/^mail-status-/)).toHaveTextContent(
      "Повтор",
    );
  }, 20_000);
});

describe("галерея версии 2", () => {
  const entries = getAdminMailLogGallery().flatMap((g) => g.entries);

  it("есть состояния повтора и окна пачки", () => {
    const ids = entries.map((e) => e.id);
    for (const id of [
      "mail_list_retrying",
      "mail_card_retrying",
      "mail_card_resend",
      "mail_card_stale",
      "mail_card_resent_copy",
      "mail_batch_preview",
      "mail_batch_nothing",
      "mail_batch_failed",
    ]) {
      expect(ids).toContain(id);
    }
  });

  it.each(["ru", "en"])(
    "язык %s: окна пачки рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries.filter((e) =>
        e.id.startsWith("mail_batch_"),
      )) {
        const { container, unmount } = render(wrap(entry.render()));
        await waitFor(() => {
          expect(container.textContent).not.toBe("");
        });
        expect(container.textContent).not.toMatch(
          /\b(batch|resend|card)\.[a-z]+[A-Za-z_.]*/,
        );
        unmount();
      }
    },
    30_000,
  );
});
