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
import { i18n, useListQueryState } from "@shared/lib";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { MAIL_LOG_LIST } from "./api/mailLogQueries";
import type { MailLogEntry } from "./api/schemas";
import { ensureAdminMailLocales } from "./lib/locales";
import { mailWhen } from "./lib/when";
import {
  MAIL_LOG_PAGES,
  MAIL_LOG_SUMMARIES,
  MAIL_NOW,
  type MailLogPageState,
  type MailLogSummaryState,
} from "./testing";
import { MailLog } from "./ui/MailLog";
import { MailLogView } from "./ui/MailLogView";
import { getAdminMailLogGallery } from "./ui/mailLogGallery";

// Раздел «Письма», список (docs/design/mail-log.md, 4.1, срез W2): полоса за сутки и подсказки,
// плашка без SMTP, фильтры в адресе, пустые состояния, телефонные карточки; затем раздел целиком
// на демо-мире и записи галереи.

const NOW = Date.parse(MAIL_NOW);
const noop = () => undefined;

/** Адрес страницы для проверок: фильтры и открытое письмо живут в нём. */
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

type ViewDemoProps = {
  page?: MailLogPageState;
  summary?: MailLogSummaryState | null;
  failed?: boolean;
  onOpen?: (row: MailLogEntry) => void;
};

const ViewDemo = ({
  page = "mixed",
  summary = "normal",
  failed = false,
  onOpen = noop,
}: ViewDemoProps) => {
  const state = useListQueryState(MAIL_LOG_LIST);
  const data = MAIL_LOG_PAGES[page];
  const rows = failed ? [] : data.items;
  return (
    <MailLogView
      state={state}
      rows={rows}
      loading={false}
      failed={failed}
      pagination={{
        mode: "cursor",
        shown: rows.length,
        hasMore: data.next_cursor !== null,
        onLoadMore: noop,
        loading: false,
        totalEstimate: data.total_estimate,
      }}
      summary={summary === null ? null : MAIL_LOG_SUMMARIES[summary]}
      now={NOW}
      selectedId={null}
      onOpen={onOpen}
      onRefresh={noop}
      onRetry={noop}
    />
  );
};

const view = (props: ViewDemoProps = {}, url?: string) =>
  wrap(<ViewDemo {...props} />, url);

beforeAll(async () => {
  installServerDemo();
  await ensureAdminMailLocales();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  activateServerScenario("admin_ready");
});
afterEach(cleanup);

describe("время строки", () => {
  const at = (iso: string) => mailWhen(iso, NOW, "ru-RU");

  it("сегодня, вчера и раньше считаются по местным суткам", () => {
    const today = new Date(NOW);
    today.setHours(0, 5, 0, 0);
    const yesterday = new Date(today.getTime() - 3600 * 1000);
    const earlier = new Date(today.getTime() - 30 * 3600 * 1000);
    expect(at(today.toISOString())?.day).toBe("today");
    expect(at(yesterday.toISOString())?.day).toBe("yesterday");
    expect(at(earlier.toISOString())?.day).toBe("earlier");
  });

  it("мусор вместо даты не ломает строку", () => {
    expect(at("not-a-date")).toBeNull();
  });
});

describe("список на эталонах", () => {
  it("строка: вид, тема, адрес с именем, итог с причиной, кто вызвал", () => {
    render(view());
    const rows = MAIL_LOG_PAGES.mixed.items;
    const failed = rows.find((e) => e.failure?.smtp_code === 550);
    const skipped = rows.find((e) => e.reason === "email_unverified");
    const anon = rows.find((e) => e.cause === "anonymous");
    const system = rows.find((e) => e.task === "signing_reminders");
    const gone = rows.find((e) => !e.template_known);
    if (!failed || !skipped || !anon || !system || !gone) {
      throw new Error("в обычном дне нет нужных строк");
    }
    expect(
      screen.getByTestId(`mail-status-${String(failed.id)}`),
    ).toHaveTextContent(
      "Не ушло550 · SMTP-сервер отказался принять письмо для этого адреса",
    );
    expect(
      screen.getByTestId(`mail-status-${String(skipped.id)}`),
    ).toHaveTextContent("Не отправлялосьпочта не подтверждена");
    const table = screen.getByRole("table", { name: "Журнал писем" });
    expect(table).toHaveTextContent("Запрос без входа");
    expect(table).toHaveTextContent("Фоновая задачаавтонапоминания маршрута");
    expect(screen.getByTestId(`mail-row-${String(gone.id)}`)).toHaveTextContent(
      `Вид удалён: ${gone.template}`,
    );
    expect(table).toHaveTextContent("Сброс пароля");
  });

  it("строка открывает карточку", async () => {
    const opened: number[] = [];
    const user = userEvent.setup();
    render(view({ onOpen: (row) => opened.push(row.id) }));
    const first = MAIL_LOG_PAGES.mixed.items[0];
    if (!first) throw new Error("пустой день");
    await user.click(screen.getByTestId(`mail-row-${String(first.id)}`));
    expect(opened).toEqual([first.id]);
  });

  it("полоса за сутки и клик по «Не ушло» ставит фильтр за сутки", async () => {
    const user = userEvent.setup();
    render(view());
    const s = MAIL_LOG_SUMMARIES.normal;
    expect(screen.getByTestId("mail-day-sent")).toHaveTextContent(
      `Отправлено ${String(s.sent)}`,
    );
    expect(screen.getByTestId("mail-day-skipped")).toHaveTextContent(
      `Не отправлялось ${String(s.not_sent + s.suppressed)}`,
    );
    expect(screen.queryByTestId("mail-smtp-off")).toBeNull();
    await user.click(screen.getByTestId("mail-day-failed"));
    const yesterday = new Date(NOW - 24 * 3600 * 1000);
    const day = `${String(yesterday.getFullYear())}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`;
    expect(where()).toContain("status=failed");
    expect(where()).toContain(`from=${day}`);
    expect(screen.getByText("Итог:")).toBeInTheDocument();
  });

  it("без сбоев «Не ушло» не кнопка, подсказки нет", () => {
    render(view({ summary: "quiet", page: "empty" }));
    expect(screen.getByTestId("mail-day-failed").tagName).toBe("SPAN");
    expect(screen.queryByTestId("mail-hint")).toBeNull();
  });

  it("почта не настроена: плашка со ссылкой на блок «Почта (SMTP)»", () => {
    render(view({ page: "smtp_off", summary: "smtp_off" }));
    expect(screen.getByTestId("mail-smtp-off")).toHaveTextContent(
      "Почта не настроена. Письма не уходят",
    );
    expect(screen.getByTestId("mail-smtp-setup")).toHaveAttribute(
      "href",
      "/admin/settings#admin-smtp",
    );
    expect(screen.getAllByText("почта не настроена").length).toBeGreaterThan(0);
  });

  it("сбой входа на SMTP: подсказка auth со ссылкой на настройки", () => {
    render(view({ page: "auth_failure", summary: "auth_failure" }));
    const hint = screen.getByTestId("mail-hint");
    expect(hint).toHaveAttribute("data-hint", "auth");
    expect(hint).toHaveTextContent(
      "SMTP-сервер отклоняет вход. Проверьте логин и пароль в блоке «Почта (SMTP)».",
    );
    expect(screen.getByTestId("mail-hint-open")).toHaveAttribute(
      "href",
      "/admin/settings#admin-smtp",
    );
  });

  it("шапка: срок хранения из сводки и ссылка на «Хранение данных»", () => {
    render(view());
    expect(screen.getByTestId("mail-log")).toHaveTextContent(
      "за последние 90 дн.",
    );
    expect(screen.getByTestId("mail-retention")).toHaveAttribute(
      "href",
      "/admin/data",
    );
  });

  it("пусто, ничего не нашлось и ошибка", async () => {
    const { unmount } = render(view({ page: "empty", summary: "quiet" }));
    expect(screen.getByText("Писем пока не было")).toBeInTheDocument();
    unmount();

    const user = userEvent.setup();
    const second = render(
      view({ page: "nothing_found" }, "/admin/mail?q=nobody"),
    );
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    await waitFor(() => {
      expect(where()).toBe("/admin/mail");
    });
    second.unmount();

    render(view({ failed: true, summary: null }));
    expect(
      screen.getByText("Не удалось загрузить журнал писем."),
    ).toBeVisible();
  });

  it("вид письма выбирается по группам", async () => {
    const user = userEvent.setup();
    render(view());
    await user.click(screen.getByTestId("mail-filter-kind"));
    const menu = await screen.findByRole("dialog", { name: "Вид письма" });
    for (const group of [
      "Вход и аккаунт",
      "Проекты",
      "Маршрут подписания",
      "Служебные",
    ]) {
      expect(within(menu).getByText(group)).toBeInTheDocument();
    }
    await user.click(
      within(menu).getByRole("checkbox", { name: "Сброс пароля" }),
    );
    expect(where()).toContain("template=reset_password");
  });

  it("условия из адреса видны чипами: вид, итог, причина, адрес, проект", () => {
    render(
      view(
        {},
        "/admin/mail?template=invite&status=not_sent&reason=smtp_off&recipient=a%40example.org",
      ),
    );
    const search = screen.getByRole("search");
    expect(search).toHaveTextContent("Вид письма:Приглашение в Студию");
    expect(search).toHaveTextContent(
      "Итог:Не отправлялось: почта не настроена",
    );
    expect(search).toHaveTextContent("Причина:почта не настроена");
    expect(search).toHaveTextContent("Адрес:a@example.org");
  });

  it("английский словарь", async () => {
    await i18n.changeLanguage("en");
    render(view({ page: "auth_failure", summary: "auth_failure" }));
    expect(screen.getByTestId("mail-log")).toHaveTextContent("Mail");
    expect(screen.getByTestId("mail-day-failed")).toHaveTextContent("Failed");
    expect(screen.getByTestId("mail-hint")).toHaveTextContent(
      "The SMTP server rejects the sign-in.",
    );
  });
});

describe("раздел на демо-мире", () => {
  it("обычный день: строки, счётчик за сутки, строка открывает ?mail=", async () => {
    const user = userEvent.setup();
    render(wrap(<MailLog />));
    const table = await screen.findByRole("table", { name: "Журнал писем" });
    await waitFor(() => {
      expect(within(table).getAllByRole("row").length).toBeGreaterThan(5);
    });
    expect(await screen.findByTestId("mail-day-failed")).toHaveTextContent(
      /Не ушло [1-9]/,
    );
    const cell = within(table).getAllByTestId(/^mail-row-/)[0];
    if (!cell) throw new Error("нет строк");
    const id = cell.getAttribute("data-testid")?.replace("mail-row-", "");
    await user.click(cell);
    expect(where()).toBe(`/admin/mail?mail=${String(id)}`);
  }, 20_000);

  it("фильтр по итогу из адреса уходит на сервер", async () => {
    render(wrap(<MailLog />, "/admin/mail?status=failed"));
    const table = await screen.findByRole("table", { name: "Журнал писем" });
    await waitFor(() => {
      expect(
        within(table).getAllByTestId(/^mail-status-/).length,
      ).toBeGreaterThan(0);
    });
    for (const status of within(table).getAllByTestId(/^mail-status-/)) {
      expect(status).toHaveTextContent("Не ушло");
    }
  }, 20_000);

  it("почта не настроена: плашка", async () => {
    activateServerScenario("admin_sso");
    render(wrap(<MailLog />));
    expect(await screen.findByTestId("mail-smtp-off")).toBeInTheDocument();
  }, 20_000);

  it("SMTP-сервер отклоняет вход: подсказка auth", async () => {
    activateServerScenario("ops_services_degraded");
    render(wrap(<MailLog />));
    expect(await screen.findByTestId("mail-hint")).toHaveAttribute(
      "data-hint",
      "auth",
    );
  }, 20_000);

  it("чистая установка: писем пока не было", async () => {
    activateServerScenario("ops_fresh");
    render(wrap(<MailLog />));
    expect(await screen.findByText("Писем пока не было")).toBeInTheDocument();
  }, 20_000);
});

describe("галерея «Админка: письма»", () => {
  const entries = getAdminMailLogGallery().flatMap((g) => g.entries);

  it("есть состояния списка из 4.4", () => {
    const ids = entries.map((e) => e.id);
    for (const id of [
      "mail_list_day",
      "mail_list_more",
      "mail_list_empty",
      "mail_list_nothing_found",
      "mail_list_error",
      "mail_list_smtp_off",
      "mail_list_auth_failure",
      "mail_list_long",
      "mail_list_phone",
    ]) {
      expect(ids).toContain(id);
    }
  });

  it.each(["ru", "en"])(
    "язык %s: записи без демо-мира рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries.filter((e) => e.scenario === undefined)) {
        const { container, unmount } = render(wrap(entry.render()));
        await waitFor(() => {
          expect(container.textContent).not.toBe("");
        });
        expect(container.textContent).not.toMatch(
          /(?<![\s@])\b(day|hint|filter|status|reason|failure|cause|col|group|statusFilter|smtpOff|empty|mailPreview)\.[a-z]+[A-Za-z_.]*/,
        );
        unmount();
      }
    },
    30_000,
  );
});
