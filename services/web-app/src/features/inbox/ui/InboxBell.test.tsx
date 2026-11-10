import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import type { Notification } from "@entities/invitation";
import { InboxBellView, type InboxBellViewProps } from "./InboxBell";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const note = (
  id: string,
  kind: Notification["kind"],
  over: Partial<Notification> = {},
  payload: Partial<Notification["payload"]> = {},
): Notification => ({
  id,
  kind,
  created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  read_at: null,
  payload: {
    project_id: "p1",
    project_name: "ВКР",
    actor_name: "Рита",
    role: null,
    ref_id: null,
    outcome: null,
    path: null,
    excerpt: null,
    profile_id: null,
    deadline: null,
    new_version: false,
    ...payload,
  },
  ...over,
});

const Where = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
};

const Harness = ({
  initiallyOpen = false,
  ...props
}: Partial<InboxBellViewProps> & { initiallyOpen?: boolean }) => {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <button type="button">outside</button>
        <InboxBellView
          count={2}
          status="ready"
          notifications={[]}
          onRetry={vi.fn()}
          onSelect={vi.fn()}
          onMarkAll={vi.fn()}
          {...props}
          open={open}
          onOpenChange={setOpen}
        />
        <Where />
      </MemoryRouter>
    </I18nextProvider>
  );
};

const bell = () => screen.getByTestId("inbox-bell");

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});
afterEach(cleanup);

describe("InboxBellView: значок", () => {
  it("показывает число и подписывает его для скринридера", () => {
    render(<Harness count={3} />);
    expect(bell()).toHaveAccessibleName("Входящие: 3 новых");
    expect(screen.getByTestId("inbox-bell-badge")).toHaveTextContent("3");
    expect(bell()).toHaveAttribute("aria-haspopup", "dialog");
  });

  it("без непрочитанного нет индикатора", () => {
    render(<Harness count={0} />);
    expect(screen.queryByTestId("inbox-bell-badge")).toBeNull();
    expect(bell()).toHaveAccessibleName("Входящие");
  });

  it("больше 99 показывает 99+", () => {
    render(<Harness count={240} />);
    expect(screen.getByTestId("inbox-bell-badge")).toHaveTextContent("99+");
  });
});

describe("InboxBellView: открытие и закрытие", () => {
  it("нажатие открывает окошко без перехода, второе нажатие закрывает", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
    expect(bell()).toHaveAttribute("aria-expanded", "false");
    await user.click(bell());
    expect(screen.getByRole("dialog", { name: "Уведомления" })).toBeVisible();
    expect(bell()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("where")).toHaveTextContent("/");
    await user.click(bell());
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
  });

  it("Esc закрывает окошко и возвращает фокус на колокольчик", async () => {
    const user = userEvent.setup();
    render(<Harness notifications={[note("n1", "invitation_accepted")]} />);
    await user.click(bell());
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
    expect(bell()).toHaveFocus();
  });

  it("клик вне окошка закрывает его", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(bell());
    await user.click(screen.getByRole("button", { name: "outside" }));
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
  });

  it("«Показать все» ведёт на страницу входящих и закрывает окошко", async () => {
    const user = userEvent.setup();
    render(<Harness initiallyOpen />);
    await user.click(screen.getByTestId("inbox-popover-all"));
    expect(screen.getByTestId("where")).toHaveTextContent("/inbox");
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
  });
});

describe("InboxBellView: список", () => {
  const list = [
    note("n1", "invitation_accepted", {}, { actor_name: "Дмитрий" }),
    note("n2", "review_reply", { read_at: "2026-11-03T09:00:00Z" }),
    note("n3", "project_invitation"),
  ];

  it("рисует текст, относительное время и отметку непрочитанного", async () => {
    const user = userEvent.setup();
    render(<Harness notifications={list} />);
    await user.click(bell());
    const items = screen.getByRole("list", { name: "Последние уведомления" });
    expect(items.querySelectorAll("li")).toHaveLength(3);
    const first = screen.getByTestId("inbox-popover-item-n1");
    expect(first).toHaveTextContent("Приглашение в «ВКР» принято: Дмитрий");
    expect(first).toHaveTextContent("5 минут назад");
    expect(first).toHaveAttribute("data-unread", "true");
    expect(first).toHaveTextContent("Новое");
    expect(screen.getByTestId("inbox-popover-item-n2")).toHaveAttribute(
      "data-unread",
      "false",
    );
    expect(screen.getByTestId("inbox-popover-item-n3")).toHaveTextContent(
      "нужно решение",
    );
  });

  it("при открытии фокус уходит на первое уведомление, стрелки двигают его", async () => {
    const user = userEvent.setup();
    render(<Harness notifications={list} initiallyOpen />);
    const [a, b, c] = ["n1", "n2", "n3"].map((id) =>
      screen.getByTestId(`inbox-popover-item-${id}`),
    );
    expect(a).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(b).toHaveFocus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(a).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(c).toHaveFocus();
    await user.keyboard("{Home}");
    expect(a).toHaveFocus();
    await user.keyboard("{End}");
    expect(c).toHaveFocus();
  });

  it("клик по уведомлению отдаёт его наверх", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness notifications={list} onSelect={onSelect} initiallyOpen />);
    await user.click(screen.getByTestId("inbox-popover-item-n2"));
    expect(onSelect).toHaveBeenCalledWith(list[1]);
  });

  it("«Отметить всё прочитанным» только при непрочитанных", async () => {
    const user = userEvent.setup();
    const onMarkAll = vi.fn();
    const { unmount } = render(
      <Harness notifications={list} onMarkAll={onMarkAll} initiallyOpen />,
    );
    await user.click(screen.getByTestId("inbox-popover-mark-all"));
    expect(onMarkAll).toHaveBeenCalledTimes(1);
    unmount();
    render(
      <Harness
        notifications={[note("n9", "review_reply", { read_at: "x" })]}
        initiallyOpen
      />,
    );
    expect(screen.queryByTestId("inbox-popover-mark-all")).toBeNull();
  });
});

describe("InboxBellView: состояния", () => {
  it("пусто", () => {
    render(<Harness status="ready" initiallyOpen />);
    expect(screen.getByTestId("inbox-popover-empty")).toHaveTextContent(
      "Новых уведомлений нет",
    );
    expect(screen.queryByTestId("inbox-popover-list")).toBeNull();
  });

  it("загрузка", () => {
    render(<Harness status="loading" initiallyOpen />);
    expect(screen.getByTestId("inbox-popover-loading")).toHaveTextContent(
      "Загружаем уведомления",
    );
  });

  it("ошибка с «Повторить»", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<Harness status="error" onRetry={onRetry} initiallyOpen />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Не удалось загрузить уведомления",
    );
    await user.click(screen.getByTestId("inbox-popover-retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    render(<Harness count={1} status="ready" initiallyOpen />);
    expect(bell()).toHaveAccessibleName("Inbox: 1 new");
    expect(screen.getByTestId("inbox-popover-empty")).toHaveTextContent(
      "No new notifications",
    );
    expect(screen.getByTestId("inbox-popover-all")).toHaveTextContent(
      "Show all",
    );
  });
});

describe("InboxBellView: маршрут подписания", () => {
  it("строка «Ждут вашей подписи» ведёт в раздел «На подпись» и закрывает окошко", async () => {
    const user = userEvent.setup();
    render(<Harness signingTasks={2} initiallyOpen />);
    const row = screen.getByTestId("inbox-popover-signing");
    expect(row).toHaveTextContent("Ждут вашей подписи: 2");
    expect(row).toHaveFocus();
    await user.click(row);
    expect(screen.getByTestId("where")).toHaveTextContent("/inbox?tab=signing");
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
  });

  it("без задач строки нет", () => {
    render(<Harness initiallyOpen />);
    expect(screen.queryByTestId("inbox-popover-signing")).toBeNull();
  });

  it("стрелки ходят от строки задач к уведомлениям", async () => {
    const user = userEvent.setup();
    render(
      <Harness
        signingTasks={1}
        notifications={[note("n1", "invitation_accepted")]}
        initiallyOpen
      />,
    );
    expect(screen.getByTestId("inbox-popover-signing")).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByTestId("inbox-popover-item-n1")).toHaveFocus();
  });

  it("запрос подписи показывает проект и срок, итог только проект", () => {
    render(
      <Harness
        initiallyOpen
        notifications={[
          note(
            "s1",
            "signing_request",
            {},
            {
              actor_name: "Иванов И. И.",
              project_name: "Bertie",
              ref_id: "sr_1",
              profile_id: "topic-approval",
              excerpt: "Заявка на тему КП",
              outcome: "approve_sign",
              deadline: "2026-11-15T12:00:00Z",
            },
          ),
          note(
            "s2",
            "signing_completed",
            {},
            {
              project_name: "Bertie",
              excerpt: "Заявка на тему КП",
              deadline: "2026-11-15T12:00:00Z",
            },
          ),
        ]}
      />,
    );
    const request = screen.getByTestId("inbox-popover-item-s1");
    expect(request).toHaveTextContent(
      "Иванов И. И. просит подписать: Заявка на тему КП",
    );
    expect(request).toHaveTextContent(
      /5 минут назад · Bertie · срок 15 ноября/,
    );
    const done = screen.getByTestId("inbox-popover-item-s2");
    expect(done).toHaveTextContent("Все подписали: Заявка на тему КП");
    expect(done).toHaveTextContent(/5 минут назад · Bertie$/);
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    render(<Harness signingTasks={3} initiallyOpen />);
    expect(screen.getByTestId("inbox-popover-signing")).toHaveTextContent(
      "Waiting for your signature: 3",
    );
  });
});
