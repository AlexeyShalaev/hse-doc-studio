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
import type { MailLogDetail, MailLogEntry } from "./api/schemas";
import { ensureAdminMailLocales } from "./lib/locales";
import { mailDuration, mailNextKey, mailNextSteps } from "./lib/mailLog";
import {
  MAIL_JOURNALS,
  MAIL_LOG_DETAILS,
  MAIL_LOG_MISSING_ID,
  MAIL_LOG_RECORDS,
  MAIL_NOW,
  makeMailLogDetail,
} from "./testing";
import { MailLog } from "./ui/MailLog";
import { MailLogCardView, type MailLogCardState } from "./ui/MailLogCardView";
import { getAdminMailLogGallery } from "./ui/mailLogGallery";

// Карточка письма (docs/design/mail-log.md, 4.2, срез W3): «Что можно сделать» по итогу и виду,
// пометки и песочница превью, итог сбоя и пропуска, сведения; затем карточка в разделе на
// демо-мире (?mail=, закрытие, переход к письмам адресата, 404) и записи галереи.

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

const view = (
  detail: MailLogDetail | null,
  options: {
    state?: MailLogCardState;
    row?: MailLogEntry | null;
    onShowRecipient?: (entry: MailLogEntry) => void;
    onShowProject?: (id: string) => void;
  } = {},
) =>
  render(
    wrap(
      <MailLogCardView
        entry={detail?.entry ?? options.row ?? null}
        detail={detail}
        state={options.state ?? (detail ? "ready" : "loading")}
        now={NOW}
        onRetry={noop}
        onClose={noop}
        onShowRecipient={options.onShowRecipient ?? noop}
        onShowProject={options.onShowProject ?? noop}
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

describe("что можно сделать", () => {
  const steps = (
    template: string,
    status: MailLogEntry["status"],
    reason: string | null = null,
  ) =>
    mailNextSteps({ template, status, reason }).map((s) =>
      s.kind === "template" ? s.key : s.kind,
    );

  it("письма со ссылкой и тестовое письмо: своя подсказка", () => {
    expect(steps("reset_password", "sent")).toEqual(["reset_password"]);
    expect(steps("verify_email", "sent")).toEqual(["verify_email"]);
    expect(steps("invite", "sent")).toEqual(["invite"]);
    expect(steps("email_change", "sent")).toEqual(["email_change"]);
    expect(steps("project_invitation_link", "sent")).toEqual([
      "project_invitation_link",
    ]);
    expect(steps("smtp_test", "sent")).toEqual(["smtp_test"]);
  });

  it("уведомления проектов и маршрута лежат во «Входящих», письма о действии с аккаунтом нет", () => {
    for (const template of [
      "project_invitation",
      "access_request",
      "transfer_request",
      "signing_request",
      "signing_reminder",
      "signing_completed",
    ]) {
      expect(mailNextKey(template)).toBe("inbox");
    }
    for (const template of ["reset_notice", "passkey_added", "passkey_reset"]) {
      expect(mailNextKey(template)).toBe("notice");
    }
    expect(mailNextKey("weekly_digest")).toBeNull();
  });

  it("сбой настроек почты идёт первым, сбой адреса нет", () => {
    expect(steps("signing_reminder", "failed", "auth")).toEqual([
      "checkSmtp",
      "inbox",
    ]);
    for (const reason of ["connect", "timeout", "tls"]) {
      expect(steps("invite", "failed", reason)[0]).toBe("checkSmtp");
    }
    expect(steps("invite", "failed", "recipient_refused")).toEqual(["invite"]);
  });

  it("почта не настроена и письмо не положено", () => {
    expect(steps("invite", "not_sent", "smtp_off")).toEqual([
      "smtpOff",
      "invite",
    ]);
    expect(steps("signing_request", "suppressed", "email_unverified")).toEqual([
      "suppressed",
      "inbox",
    ]);
    expect(steps("weekly_digest", "sent")).toEqual([]);
  });

  it("длительность: мс до секунды, дальше секунды", () => {
    expect(mailDuration(420)).toEqual({ unit: "ms", value: 420 });
    expect(mailDuration(1840)).toEqual({ unit: "seconds", value: 1.8 });
  });
});

describe("карточка", () => {
  it("ссылка с токеном: пометка, песочница без allow-*, текстовая часть по кнопке", async () => {
    const user = userEvent.setup();
    const detail = D.token_link;
    view(detail);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      detail.entry.subject,
    );
    expect(screen.getByTestId("mail-card-link-hidden")).toHaveTextContent(
      "Ссылка скрыта",
    );
    const frame = screen.getByTestId("mail-card-frame");
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("srcdoc")).toBe(detail.preview?.html);
    expect(screen.queryByTestId("mail-card-outcome")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mail-card-text")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("mail-card-text-toggle"));
    expect(screen.getByTestId("mail-card-text").textContent).toBe(
      detail.preview?.text,
    );
    expect(
      within(screen.getByTestId("mail-card-message-id")).getByDisplayValue(
        detail.entry.message_id ?? "",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("mail-card-when")).toHaveTextContent(
      /^Отправлено /,
    );
    expect(
      screen.getByTestId("mail-card-next").querySelector("[data-step]"),
    ).toHaveAttribute("data-step", "reset_password");
  });

  it("550: класс сбоя, ответ SMTP, сообщение не хранится, ссылки в настройки нет", () => {
    const detail = D.failed_with_note;
    view(detail);
    const outcome = screen.getByTestId("mail-card-outcome");
    expect(outcome).toHaveTextContent(
      "SMTP-сервер отказался принять письмо для этого адреса",
    );
    const reply = within(outcome).getByLabelText("Ответ SMTP");
    expect((reply as HTMLTextAreaElement).value).toMatch(/^550 /);
    expect(screen.getByTestId("mail-card-note-hidden")).toBeInTheDocument();
    expect(screen.queryByTestId("mail-card-settings")).not.toBeInTheDocument();
    expect(screen.getByTestId("mail-card-when")).toHaveTextContent(/^Попытка /);
  });

  it("сбой входа на SMTP: ссылка в настройки почты и фоновая задача", () => {
    view(D.failed_auth_system);
    expect(screen.getByTestId("mail-card-settings")).toHaveAttribute(
      "href",
      "/admin/settings#admin-smtp",
    );
    expect(screen.getByTestId("mail-card-check-smtp")).toBeInTheDocument();
    expect(screen.getByTestId("mail-card-actor")).toHaveTextContent(
      "Фоновая задача: автонапоминания маршрута",
    );
    expect(screen.getByTestId("mail-card-origin")).toHaveTextContent(
      "Автонапоминание маршрута",
    );
  });

  it("перерисовано и вид удалён", () => {
    view(D.rerendered);
    expect(screen.getByTestId("mail-card-rerendered")).toBeInTheDocument();
    cleanup();
    view(D.template_gone);
    expect(screen.getByTestId("mail-card-template-gone")).toHaveTextContent(
      "Такого вида письма в этой версии Студии больше нет",
    );
    expect(screen.queryByTestId("mail-card-frame")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mail-card-next")).not.toBeInTheDocument();
  });

  it("не положено: причина в итоге и «это не сбой»", () => {
    view(D.suppressed);
    expect(screen.getByTestId("mail-card-reason")).toHaveTextContent(
      "Почта не подтверждена",
    );
    expect(screen.getByTestId("mail-card-next")).toHaveTextContent(
      "Письмо не отправлялось: почта не подтверждена. Это не сбой",
    );
  });

  it("почта не настроена: ссылка «Настроить почту»", () => {
    view(D.not_sent);
    const next = screen.getByTestId("mail-card-next");
    expect(
      within(next).getByRole("link", { name: "Настроить почту" }),
    ).toHaveAttribute("href", "/admin/settings#admin-smtp");
  });

  it("проект и вызвавший удалены", () => {
    view(D.project_gone);
    expect(screen.getByTestId("mail-card-project")).toHaveTextContent(
      "Проект удалён",
    );
    expect(screen.getByTestId("mail-card-actor")).toHaveTextContent(
      "Пользователь удалён",
    );
  });

  it("человек: ссылка на карточку в «Пользователях», проект ставит фильтр", async () => {
    const user = userEvent.setup();
    const detail = makeMailLogDetail(MAIL_LOG_RECORDS.signing_page);
    const projects: string[] = [];
    const recipients: MailLogEntry[] = [];
    view(detail, {
      onShowProject: (id) => projects.push(id),
      onShowRecipient: (e) => recipients.push(e),
    });
    const to = screen.getByTestId("mail-card-to");
    const person = detail.entry.to_user;
    if (!person) throw new Error("у письма нет человека");
    expect(within(to).getByRole("link", { name: person.name })).toHaveAttribute(
      "href",
      `/admin/users?user=${person.id}`,
    );
    await user.click(
      within(screen.getByTestId("mail-card-project")).getByRole("button"),
    );
    expect(projects).toEqual([detail.entry.project?.id]);
    await user.click(screen.getByTestId("mail-card-show-all"));
    expect(recipients.map((e) => e.id)).toEqual([detail.entry.id]);
  });

  it("грузится: шапка и сведения из строки, превью ждёт", () => {
    const row = D.token_link.entry;
    view(null, { row, state: "loading" });
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      row.subject,
    );
    expect(screen.getByTestId("mail-card-to")).toHaveTextContent(row.to_email);
    expect(screen.getByTestId("mail-card-loading")).toBeInTheDocument();
  });

  it("404: письмо не найдено", () => {
    view(null, { state: "not_found" });
    expect(screen.getByTestId("mail-card-not-found")).toHaveTextContent(
      "Письмо не найдено",
    );
  });
});

describe("карточка в разделе на демо-мире", () => {
  const token = MAIL_LOG_RECORDS.token_link.entry;

  it("?mail открывает карточку, крестик убирает параметр", async () => {
    const user = userEvent.setup();
    render(wrap(<MailLog />, `/admin/mail?mail=${String(token.id)}`));
    const card = await screen.findByTestId("mail-card");
    expect(
      await within(card).findByTestId("mail-card-frame"),
    ).toBeInTheDocument();
    expect(card).toHaveAttribute("role", "dialog");
    expect(within(card).getByRole("heading", { level: 2 })).toHaveTextContent(
      token.subject,
    );
    await user.click(within(card).getByTestId("mail-card-close"));
    await waitFor(() => {
      expect(where()).toBe("/admin/mail");
    });
  }, 20_000);

  it("письма адресату: человек по recipient_id, прочие условия снимаются", async () => {
    const user = userEvent.setup();
    render(
      wrap(<MailLog />, `/admin/mail?status=sent&q=x&mail=${String(token.id)}`),
    );
    const card = await screen.findByTestId("mail-card");
    await user.click(await within(card).findByTestId("mail-card-show-all"));
    await waitFor(() => {
      expect(where()).toBe(
        `/admin/mail?recipient_id=${token.to_user?.id ?? ""}`,
      );
    });
  }, 20_000);

  it("письма адресату без аккаунта: точный адрес", async () => {
    const user = userEvent.setup();
    const stranger = MAIL_JOURNALS.default.find(
      (r) => r.entry.to_user === null,
    )?.entry;
    if (!stranger) throw new Error("нет письма на чужой адрес");
    render(wrap(<MailLog />, `/admin/mail?mail=${String(stranger.id)}`));
    const card = await screen.findByTestId("mail-card");
    await user.click(await within(card).findByTestId("mail-card-show-all"));
    await waitFor(() => {
      expect(new URLSearchParams(where().split("?")[1]).get("recipient")).toBe(
        stranger.to_email,
      );
    });
    expect(where()).not.toContain("mail=");
  }, 20_000);

  it("запись удалена по сроку: «Письмо не найдено»", async () => {
    render(
      wrap(<MailLog />, `/admin/mail?mail=${String(MAIL_LOG_MISSING_ID)}`),
    );
    expect(await screen.findByTestId("mail-card-not-found")).toHaveTextContent(
      "Письмо не найдено",
    );
  }, 20_000);
});

describe("галерея: карточка", () => {
  const entries = getAdminMailLogGallery().flatMap((g) => g.entries);

  it("есть состояния карточки из 4.4", () => {
    const ids = entries.map((e) => e.id);
    for (const id of [
      "mail_card_token_link",
      "mail_card_page_link",
      "mail_card_failed_note",
      "mail_card_failed_auth",
      "mail_card_rerendered",
      "mail_card_template_gone",
      "mail_card_suppressed",
      "mail_card_not_sent",
      "mail_card_anonymous",
      "mail_card_system",
      "mail_card_not_found",
      "mail_card_phone",
    ]) {
      expect(ids).toContain(id);
    }
  });

  it.each(["ru", "en"])(
    "язык %s: карточки рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries.filter(
        (e) => e.id.startsWith("mail_card_") && e.scenario === undefined,
      )) {
        const { container, unmount } = render(wrap(entry.render()));
        await waitFor(() => {
          expect(container.textContent).not.toBe("");
        });
        expect(container.textContent).not.toMatch(
          /(?<![\s@/])\b(card|origin|ref|cause|status|reason|failure|hint)\.[a-z]+[A-Za-z_.]*/,
        );
        unmount();
      }
    },
    30_000,
  );
});
