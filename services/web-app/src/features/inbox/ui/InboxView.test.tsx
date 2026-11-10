import { useState } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { Notification } from "@entities/invitation";
import type { SigningTaskSummary } from "@entities/signing-route";
import { inboxTabOf, type InboxTab } from "../lib/inboxTab";
import { InboxView, type InboxViewProps } from "./InboxView";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const DAY = 24 * 60 * 60 * 1000;
const inDays = (days: number) =>
  new Date(Date.now() + days * DAY).toISOString();

const task = (over: Partial<SigningTaskSummary> = {}): SigningTaskSummary => ({
  project: { id: "p1", name: "Bertie: курсовой проект" },
  route_id: "sr_1",
  profile: {
    id: "topic-approval",
    name: { ru: "Заявка на тему КП", en: "Course project topic application" },
  },
  round: 1,
  sender: "Иванов И. И.",
  deadline: inDays(5),
  next_action: "approve_and_sign",
  since: inDays(-1),
  ...over,
});

const note = (
  id: string,
  kind: Notification["kind"],
  payload: Partial<Notification["payload"]> = {},
): Notification => ({
  id,
  kind,
  created_at: "2026-11-03T09:00:00Z",
  read_at: null,
  payload: {
    project_id: "p1",
    project_name: "Bertie",
    actor_name: "Иванов И. И.",
    role: null,
    ref_id: "sr_1",
    outcome: null,
    path: null,
    excerpt: "Заявка на тему КП",
    profile_id: "topic-approval",
    deadline: null,
    new_version: false,
    ...payload,
  },
});

const Harness = ({
  initialTab = "all",
  ...props
}: Partial<InboxViewProps> & { initialTab?: InboxTab }) => {
  const [tab, setTab] = useState<InboxTab>(initialTab);
  return (
    <I18nextProvider i18n={i18n}>
      <InboxView
        invitations={[]}
        transfers={[]}
        notifications={[]}
        myRequests={[]}
        signingTasks={[]}
        signingStatus="ready"
        onInvitation={vi.fn()}
        onTransfer={vi.fn()}
        onRequestDecision={vi.fn()}
        onNotification={vi.fn()}
        onMarkAll={vi.fn()}
        onCancelRequest={vi.fn()}
        onSigningTask={vi.fn()}
        onSigningRetry={vi.fn()}
        {...props}
        tab={tab}
        onTab={setTab}
      />
    </I18nextProvider>
  );
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("«Входящие»: раздел «На подпись»", () => {
  it("карточка называет точку, проект, отправителя, что нужно и срок", async () => {
    const user = userEvent.setup();
    const onSigningTask = vi.fn();
    const item = task();
    render(<Harness signingTasks={[item]} onSigningTask={onSigningTask} />);
    const section = screen.getByRole("region", { name: /На подпись/ });
    const card = within(section).getByTestId("inbox-signing-task-sr_1");
    expect(card).toHaveTextContent("Заявка на тему КП");
    expect(card).toHaveTextContent(
      "Bertie: курсовой проект · просит Иванов И. И.",
    );
    expect(within(card).getByTestId("inbox-signing-action")).toHaveTextContent(
      "Согласовать и подписать",
    );
    expect(
      within(card).getByTestId("inbox-signing-deadline"),
    ).toHaveTextContent(/^срок \d+ [а-я]+$/);
    expect(card).toHaveAttribute("data-overdue", "false");
    expect(screen.getByTestId("inbox-tab-signing-count")).toHaveTextContent(
      "1",
    );
    expect(screen.queryByTestId("inbox-empty")).toBeNull();

    await user.click(
      screen.getByRole("button", {
        name: "Открыть страницу подписи: Заявка на тему КП",
      }),
    );
    expect(onSigningTask).toHaveBeenCalledWith(item);
  });

  it("просроченный срок выделен, просроченные идут первыми", () => {
    render(
      <Harness
        signingTasks={[
          task({ route_id: "sr_later", deadline: inDays(10) }),
          task({ route_id: "sr_none", deadline: null, next_action: "sign" }),
          task({
            route_id: "sr_late",
            deadline: inDays(-2),
            next_action: "approve",
          }),
        ]}
      />,
    );
    const cards = screen.getAllByTestId(/^inbox-signing-task-/);
    expect(cards.map((c) => c.dataset.testid)).toEqual([
      "inbox-signing-task-sr_late",
      "inbox-signing-task-sr_later",
      "inbox-signing-task-sr_none",
    ]);
    const late = screen.getByTestId("inbox-signing-task-sr_late");
    expect(late).toHaveAttribute("data-overdue", "true");
    expect(
      within(late).getByTestId("inbox-signing-deadline"),
    ).toHaveTextContent(/^срок прошёл /);
    expect(within(late).getByTestId("inbox-signing-action")).toHaveTextContent(
      "Согласовать",
    );
    const none = screen.getByTestId("inbox-signing-task-sr_none");
    expect(within(none).queryByTestId("inbox-signing-deadline")).toBeNull();
    expect(within(none).getByTestId("inbox-signing-action")).toHaveTextContent(
      "Подписать итоговый PDF",
    );
  });

  it("во вкладке «Всё» без задач раздела нет, пусто общее", () => {
    render(<Harness />);
    expect(screen.queryByTestId("inbox-signing")).toBeNull();
    expect(screen.getByTestId("inbox-empty")).toHaveTextContent(
      "Здесь будут документы на подпись, приглашения, запросы и уведомления",
    );
  });

  it("вкладка «На подпись» без задач говорит, что ничего не ждёт", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByTestId("inbox-tab-signing"));
    expect(screen.getByTestId("inbox-signing-empty")).toHaveTextContent(
      "Ничего не ждёт вашей подписи",
    );
    expect(screen.queryByTestId("inbox-empty")).toBeNull();
  });

  it("загрузка и ошибка с «Повторить»", async () => {
    const user = userEvent.setup();
    const onSigningRetry = vi.fn();
    const { rerender } = render(
      <Harness initialTab="signing" signingStatus="loading" />,
    );
    expect(screen.getByTestId("inbox-signing-loading")).toHaveTextContent(
      "Загружаем документы на подпись",
    );
    rerender(
      <Harness
        initialTab="signing"
        signingStatus="error"
        onSigningRetry={onSigningRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Не удалось загрузить документы на подпись",
    );
    await user.click(screen.getByTestId("inbox-signing-retry"));
    expect(onSigningRetry).toHaveBeenCalledTimes(1);
  });

  it("ошибка видна и во вкладке «Всё»", () => {
    render(<Harness signingStatus="error" />);
    expect(screen.getByTestId("inbox-signing-error")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox-empty")).toBeNull();
  });

  it("вкладка «На подпись» показывает только уведомления маршрутов", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        notifications={[
          note("n1", "signing_returned", { excerpt: "Поправьте тему" }),
          note("n2", "invitation_accepted", { ref_id: null }),
        ]}
      />,
    );
    expect(screen.getByTestId("inbox-notification-n2")).toBeInTheDocument();
    await user.click(screen.getByTestId("inbox-tab-signing"));
    expect(screen.getByTestId("inbox-notification-n1")).toHaveTextContent(
      "Возвращено на доработку (Иванов И. И.): «Поправьте тему» · Bertie",
    );
    expect(screen.queryByTestId("inbox-notification-n2")).toBeNull();
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    render(
      <Harness
        lang="en"
        signingTasks={[task({ deadline: inDays(-1), next_action: "approve" })]}
      />,
    );
    const card = screen.getByTestId("inbox-signing-task-sr_1");
    expect(card).toHaveTextContent("Course project topic application");
    expect(card).toHaveTextContent("from Иванов И. И.");
    expect(card).toHaveTextContent("Approve");
    expect(card).toHaveTextContent(/overdue since /);
    expect(screen.getByTestId("inbox-tab-signing")).toHaveTextContent(
      "To sign",
    );
  });
});

describe("«Входящие»: тексты уведомлений маршрута", () => {
  const text = (n: Notification) => {
    render(<Harness notifications={[n]} />);
    const found = screen.getByTestId(`inbox-notification-${n.id}`).textContent;
    cleanup();
    return found;
  };

  it("ход запроса и напоминания, срок рядом с проектом", () => {
    expect(
      text(
        note("a", "signing_request", {
          outcome: "approve",
          deadline: "2026-11-15T12:00:00Z",
        }),
      ),
    ).toMatch(
      /^Иванов И\. И\. просит согласовать: Заявка на тему КП · Bertie · срок 15 ноября( 2026 г\.)?/,
    );
    expect(
      text(note("b", "signing_request", { outcome: "approve_sign" })),
    ).toMatch(/^Иванов И\. И\. просит подписать: Заявка на тему КП · Bertie/);
    expect(text(note("c", "signing_request", { outcome: "sign" }))).toMatch(
      /^Подпишите итоговый PDF: Заявка на тему КП/,
    );
    expect(text(note("d", "signing_reminder", { outcome: "approve" }))).toMatch(
      /^Напоминание о согласовании: Заявка на тему КП/,
    );
    expect(text(note("e", "signing_reminder", { outcome: "sign" }))).toMatch(
      /^Напоминание о подписи итогового PDF: Заявка на тему КП/,
    );
  });

  it("остановка называет причину, итог и отмена без срока", () => {
    expect(text(note("a", "signing_paused", { outcome: "rebuilt" }))).toMatch(
      /^Документ изменился, маршрут остановлен: Заявка на тему КП · Bertie/,
    );
    expect(
      text(note("b", "signing_paused", { outcome: "participant_left" })),
    ).toMatch(/^Участник маршрута ушёл из проекта, назначьте другого/);
    expect(
      text(
        note("c", "signing_completed", { deadline: "2026-11-15T12:00:00Z" }),
      ),
    ).toMatch(/^Все подписали: Заявка на тему КП · Bertie\d/);
    expect(text(note("d", "signing_cancelled"))).toMatch(
      /^Маршрут отменён: Заявка на тему КП/,
    );
  });

  it("без имени вернувшего пишет «Участник»", () => {
    expect(
      text(
        note("a", "signing_returned", {
          actor_name: null,
          excerpt: "Нет подписи",
        }),
      ),
    ).toMatch(/^Возвращено на доработку \(Участник\): «Нет подписи»/);
  });
});

describe("вкладка из адреса", () => {
  it("известная вкладка остаётся, прочее значит «Всё»", () => {
    expect(inboxTabOf("signing")).toBe("signing");
    expect(inboxTabOf("transfers")).toBe("transfers");
    expect(inboxTabOf("nope")).toBe("all");
    expect(inboxTabOf(null)).toBe("all");
  });
});
