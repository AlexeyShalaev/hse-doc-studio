import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { I18nextProvider } from "react-i18next";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { i18n, useToastStore } from "@shared/lib";
import { ProjectAccessPanel } from "@features/project-access";
import { InboxBell, InboxPanel } from "@features/inbox";
import { inboxApi } from "@entities/invitation";
import { TransferSection } from "@features/project-transfer";
import { ProjectInvitePage } from "@pages/ProjectInvitePage";
import { ProjectUnavailablePage } from "@pages/ProjectUnavailablePage";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";
import { signOut } from "./world";
import { invitesOf } from "./invitations";

// Трек invites поверх демо-транспорта: те же запросы, что уйдут бэкенду, и ответы через те же zod-схемы.

const mountWith = (ui: React.ReactNode, path = "/") =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          })
        }
      >
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const toastTexts = () =>
  useToastStore
    .getState()
    .toasts.map((t) => `${t.title ?? ""} ${t.message}`)
    .join("\n");

const OWN = "p_01hxa1c4de";

beforeAll(() => {
  installServerDemo();
  enableServerDemo();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  useToastStore.getState().clear();
  activateServerScenario("student_ready");
});
afterEach(cleanup);

describe("демо invites: панель «Доступ»", () => {
  it("«Ожидают» показывает приглашения и запрос, одобрение пишет участника", async () => {
    const user = userEvent.setup();
    mountWith(<ProjectAccessPanel projectId={OWN} myRole="owner" />);
    const pending = await screen.findByTestId("project-access-pending");
    expect(
      within(pending).getByTestId("invitation-row-inv_demo_user"),
    ).toHaveAttribute("data-state", "pending");
    expect(
      within(pending).getByTestId("invitation-row-inv_demo_email"),
    ).toHaveAttribute("data-state", "expired");

    await user.click(
      screen.getByTestId("access-request-approve-arq_demo_vera"),
    );
    await screen.findByTestId("access-request-approve-form");
    await user.click(screen.getByTestId("access-request-approve-submit"));
    await waitFor(() => {
      expect(toastTexts()).toContain("Вера Смирнова теперь в проекте");
    });
    const project = getServerWorld().projects.find((p) => p.summary.id === OWN);
    expect(project?.roles.u_demo_vera).toBe("reviewer");
    await waitFor(() => {
      expect(screen.queryByTestId("pending-access-requests")).toBeNull();
    });
  });

  it("ACCESS_MANAGE: редактор с «Может делиться» видит «Ожидают», обычный редактор нет", async () => {
    const world = getServerWorld();
    const project = world.projects.find((p) => p.summary.id === OWN);
    if (!project) throw new Error("demo project not found");
    const id = Object.keys(project.roles).find(
      (userId) => project.roles[userId] === "editor",
    );
    if (id === undefined) throw new Error("demo editor not found");
    const currentUser = world.bootstrap.user;
    if (currentUser === null) throw new Error("demo user not signed in");
    world.bootstrap = { ...world.bootstrap, user: { ...currentUser, id } };
    project.canShare = { [id]: true };

    mountWith(<ProjectAccessPanel projectId={OWN} myRole="editor" />);
    const pending = await screen.findByTestId("project-access-pending");
    expect(
      within(pending).getByTestId("invitation-row-inv_demo_user"),
    ).toBeTruthy();
    cleanup();

    project.canShare = { [id]: false };
    mountWith(<ProjectAccessPanel projectId={OWN} myRole="editor" />);
    await waitFor(() => {
      expect(screen.queryByTestId("project-access-pending")).toBeNull();
    });
  });

  it("приглашение по почте без SMTP отдаёт ссылку для пересылки", async () => {
    activateServerScenario("student_nosmtp");
    const user = userEvent.setup();
    mountWith(<ProjectAccessPanel projectId={OWN} myRole="owner" />);
    await user.click(await screen.findByTestId("access-invite-email"));
    const form = await screen.findByTestId("invite-form");
    expect(screen.getByTestId("invite-submit")).toBeDisabled();
    await user.type(within(form).getByTestId("invite-email"), "new@hse.ru");
    const message =
      within(form).getByTestId<HTMLTextAreaElement>("invite-message");
    // Текст уже составлен по проекту и роли: его можно заменить своим.
    await waitFor(() => {
      expect(message.value).toContain("Приглашаю вас в проект");
    });
    await user.clear(message);
    await user.type(message, "Привет");
    await user.click(screen.getByTestId("invite-submit"));
    const link = await screen.findByTestId("invite-link");
    expect(within(link).getByDisplayValue(/\/project-invite\//)).toBeTruthy();
    expect(screen.getByTestId("invite-copy")).toBeInTheDocument();
    const created = invitesOf(getServerWorld()).projectInvitations[OWN]?.[0];
    expect(created?.invitee.email_hint).toBe("new@hse.ru");
    expect(created?.message).toBe("Привет");
  });

  it("повторное приглашение того же адресата показывает отказ сервера", async () => {
    const user = userEvent.setup();
    mountWith(<ProjectAccessPanel projectId={OWN} myRole="owner" />);
    const before = invitesOf(getServerWorld()).projectInvitations[OWN]?.length;
    await user.click(await screen.findByTestId("access-invite-email"));
    await user.type(await screen.findByTestId("invite-email"), "dup@hse.ru");
    await user.click(screen.getByTestId("invite-submit"));
    await waitFor(() => {
      expect(toastTexts()).toContain("Приглашение отправлено на почту");
    });
    await user.click(screen.getByTestId("access-invite-email"));
    await user.type(await screen.findByTestId("invite-email"), "dup@hse.ru");
    await user.click(screen.getByTestId("invite-submit"));
    expect(await screen.findByTestId("invite-error")).toHaveTextContent(
      "уже отправлено приглашение",
    );
    expect(invitesOf(getServerWorld()).projectInvitations[OWN]?.length).toBe(
      (before ?? 0) + 1,
    );
  });
});

describe("демо invites: «Входящие»", () => {
  it("принятие передачи делает студента владельцем", async () => {
    const user = userEvent.setup();
    mountWith(<InboxPanel />);
    const card = await screen.findByTestId("inbox-transfer-trf_demo_mine");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await user.click(
      within(card).getByTestId("inbox-transfer-accept-trf_demo_mine"),
    );
    expect(confirm).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
    await waitFor(() => {
      expect(toastTexts()).toContain("Теперь вы владелец");
    });
    const project = getServerWorld().projects.find(
      (p) => p.summary.id === "p_01hxa3k2jm",
    );
    expect(project?.summary.owner.id).toBe("u_01hx7k2m9c");
    expect(project?.roles.u_01hx7k5pavel).toBe("editor");
  });

  it("просроченное приглашение без кнопок, отметка всего прочитанным", async () => {
    const user = userEvent.setup();
    mountWith(<InboxPanel />);
    const old = await screen.findByTestId("inbox-invitation-inv_demo_old");
    expect(old).toHaveAttribute("data-state", "expired");
    expect(within(old).queryByRole("button")).toBeNull();
    const note = screen.getByTestId("inbox-notification-ntf_demo_accepted");
    expect(note).toHaveAttribute("data-read", "false");
    await user.click(screen.getByTestId("inbox-mark-all-read"));
    await waitFor(() => {
      expect(
        screen.getByTestId("inbox-notification-ntf_demo_accepted"),
      ).toHaveAttribute("data-read", "true");
    });
  });

  it("вкладка «Приглашения» прячет передачи и уведомления", async () => {
    const user = userEvent.setup();
    mountWith(<InboxPanel />);
    await screen.findByTestId("inbox-transfer-trf_demo_mine");
    await user.click(screen.getByTestId("inbox-tab-invitations"));
    expect(screen.queryByTestId("inbox-transfer-trf_demo_mine")).toBeNull();
    expect(screen.queryByTestId("inbox-notifications")).toBeNull();
    expect(screen.getByTestId("inbox-invitation-inv_demo_mine")).toBeTruthy();
  });
});

describe("демо invites: передача владения", () => {
  it("владелец отправляет передачу человеку и может её отменить", async () => {
    const user = userEvent.setup();
    mountWith(
      <TransferSection projectId={OWN} projectName="Bertie" myRole="owner" />,
    );
    await user.click(await screen.findByTestId("project-transfer-start"));
    await user.click(
      await screen.findByTestId("transfer-target-user-u_01hx7k1a0b"),
    );
    await user.click(screen.getByTestId("transfer-submit"));
    await waitFor(() => {
      expect(screen.getByTestId("project-transfer")).toHaveAttribute(
        "data-state",
        "pending",
      );
    });
    await user.click(screen.getByTestId("project-transfer-cancel"));
    await waitFor(() => {
      expect(screen.getByTestId("project-transfer")).toHaveAttribute(
        "data-state",
        "none",
      );
    });
  });

  it("не владельцу блок не показывается", () => {
    mountWith(
      <TransferSection projectId={OWN} projectName="Bertie" myRole="editor" />,
    );
    expect(screen.queryByTestId("project-transfer")).toBeNull();
  });
});

describe("демо invites: страницы", () => {
  const invitePage = (token: string) =>
    mountWith(
      <Routes>
        <Route path="/project-invite/:token" element={<ProjectInvitePage />} />
      </Routes>,
      `/project-invite/${token}`,
    );

  it.each([
    ["hspi_demo_ok", "ok"],
    ["hspi_demo_expired", "expired"],
    ["hspi_demo_used", "used"],
    ["hspi_nope", "invalid"],
  ])("ссылка %s даёт состояние %s", async (token, state) => {
    invitePage(token);
    await waitFor(() => {
      expect(screen.getByTestId("project-invite-page")).toHaveAttribute(
        "data-state",
        state,
      );
    });
  });

  describe("возврат по ?next= (страница подписи маршрута)", () => {
    const Where = () => {
      const location = useLocation();
      return (
        <output data-testid="where">{`${location.pathname}${location.search}`}</output>
      );
    };
    const withNext = (path: string) =>
      mountWith(
        <Routes>
          <Route
            path="/project-invite/:token"
            element={<ProjectInvitePage />}
          />
          <Route path="*" element={<Where />} />
        </Routes>,
        path,
      );

    it("«Принять» ведёт на next", async () => {
      const user = userEvent.setup();
      withNext(
        `/project-invite/hspi_demo_ok?next=${encodeURIComponent("/sign/p_01hxa3k2jm/sr_demo0001")}`,
      );
      await user.click(await screen.findByTestId("project-invite-accept"));
      expect(await screen.findByTestId("where")).toHaveTextContent(
        "/sign/p_01hxa3k2jm/sr_demo0001",
      );
    });

    it("чужой адрес в next не принимается: обычный переход в проект", async () => {
      const user = userEvent.setup();
      withNext(
        `/project-invite/hspi_demo_ok?next=${encodeURIComponent("//evil.example/sign")}`,
      );
      await user.click(await screen.findByTestId("project-invite-accept"));
      expect(await screen.findByTestId("where")).toHaveTextContent(
        "/projects/p_01hxa3k2jm",
      );
    });

    it("вход и регистрация возвращают на приглашение с тем же next", async () => {
      const user = userEvent.setup();
      // Не вошёл: кнопки «Войти» и «Зарегистрироваться» вместо «Принять».
      signOut(getServerWorld());
      const next = encodeURIComponent("/sign/p_01hxa3k2jm/sr_demo0001");
      const back = encodeURIComponent(
        `/project-invite/hspi_demo_signup?next=${next}`,
      );
      withNext(`/project-invite/hspi_demo_signup?next=${next}`);
      await user.click(await screen.findByTestId("project-invite-signin"));
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/login?next=${back}`,
      );
      cleanup();
      withNext(`/project-invite/hspi_demo_signup?next=${next}`);
      await user.click(await screen.findByTestId("project-invite-signup"));
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/invite/hspi_demo_signup?next=${back}`,
      );
    });
  });

  it("страница приглашения показывает сообщение приглашающего", async () => {
    invitePage("hspi_demo_ok");
    expect(
      (await screen.findByTestId("project-invite-message")).textContent,
    ).toContain("Приглашаю вас в проект «ВКР: Анализ требований»");
  });

  it("чужая почта: принятие показывает несовпадение", async () => {
    const user = userEvent.setup();
    invitePage("hspi_demo_mismatch");
    await user.click(await screen.findByTestId("project-invite-accept"));
    await waitFor(() => {
      expect(screen.getByTestId("project-invite-page")).toHaveAttribute(
        "data-state",
        "email_mismatch",
      );
    });
  });

  it("«нет доступа»: запрос доступа с сообщением", async () => {
    const user = userEvent.setup();
    mountWith(
      <Routes>
        <Route
          path="/projects/:projectId"
          element={<ProjectUnavailablePage />}
        />
      </Routes>,
      "/projects/p_01hxa9foreign",
    );
    await user.click(await screen.findByTestId("request-access-open"));
    await user.type(screen.getByTestId("request-access-message"), "Я соавтор");
    await user.click(screen.getByTestId("request-access-submit"));
    expect(await screen.findByTestId("request-access-sent")).toBeTruthy();
  });
});

describe("демо invites: колокольчик", () => {
  const Where = () => (
    <output data-testid="where">{useLocation().pathname}</output>
  );

  it("считает непрочитанное и ожидающее, открывает окошко без перехода", async () => {
    const user = userEvent.setup();
    mountWith(
      <>
        <InboxBell />
        <Where />
      </>,
    );
    const bell = await screen.findByTestId("inbox-bell");
    await waitFor(() => {
      expect(Number(bell.getAttribute("data-count"))).toBeGreaterThan(1);
    });
    await user.click(bell);
    const list = await screen.findByTestId("inbox-popover-list");
    expect(
      within(list).getByTestId("inbox-popover-item-ntf_demo_accepted"),
    ).toHaveTextContent(
      "Приглашение в «Bertie: курсовой проект» принято: Дмитрий Кузнецов",
    );
    expect(screen.getByTestId("where")).toHaveTextContent("/");
  });

  it("клик по уведомлению отмечает его прочитанным, ведёт в проект и закрывает окошко", async () => {
    const user = userEvent.setup();
    mountWith(
      <Routes>
        <Route
          path="*"
          element={
            <>
              <InboxBell />
              <Where />
            </>
          }
        />
      </Routes>,
    );
    await user.click(await screen.findByTestId("inbox-bell"));
    await user.click(
      await screen.findByTestId("inbox-popover-item-ntf_demo_accepted"),
    );
    expect(screen.queryByTestId("inbox-popover")).toBeNull();
    expect(screen.getByTestId("where")).toHaveTextContent(
      "/projects/p_01hxa1c4de",
    );
    await waitFor(() => {
      expect(
        invitesOf(getServerWorld()).notifications.find(
          (n) => n.id === "ntf_demo_accepted",
        )?.read_at,
      ).not.toBeNull();
    });
  });

  it("непрочитанный запрос доступа ведёт на «Входящие» и остаётся непрочитанным", async () => {
    const user = userEvent.setup();
    mountWith(
      <>
        <InboxBell />
        <Where />
      </>,
    );
    await user.click(await screen.findByTestId("inbox-bell"));
    await user.click(
      await screen.findByTestId("inbox-popover-item-ntf_demo_request"),
    );
    expect(screen.getByTestId("where")).toHaveTextContent("/inbox");
    expect(
      invitesOf(getServerWorld()).notifications.find(
        (n) => n.id === "ntf_demo_request",
      )?.read_at,
    ).toBeNull();
  });

  it("«Отметить всё прочитанным» гасит точки, окошко остаётся открытым", async () => {
    const user = userEvent.setup();
    mountWith(<InboxBell />);
    await user.click(await screen.findByTestId("inbox-bell"));
    await user.click(await screen.findByTestId("inbox-popover-mark-all"));
    await waitFor(() => {
      expect(screen.queryByTestId("inbox-popover-unread-dot")).toBeNull();
    });
    expect(screen.getByTestId("inbox-popover")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox-popover-mark-all")).toBeNull();
  });

  it("ошибка загрузки показывает «Повторить», повтор находит список", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn(inboxApi, "notifications")
      .mockRejectedValueOnce(new Error("boom"));
    mountWith(<InboxBell />);
    await user.click(await screen.findByTestId("inbox-bell"));
    expect(await screen.findByTestId("inbox-popover-error")).toBeVisible();
    await user.click(screen.getByTestId("inbox-popover-retry"));
    expect(await screen.findByTestId("inbox-popover-list")).toBeVisible();
    spy.mockRestore();
  });

  it("просит у бэкенда только десять последних", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(inboxApi, "notifications");
    mountWith(<InboxBell />);
    await user.click(await screen.findByTestId("inbox-bell"));
    await screen.findByTestId("inbox-popover-list");
    expect(spy).toHaveBeenCalledWith(10);
    spy.mockRestore();
  });
});
