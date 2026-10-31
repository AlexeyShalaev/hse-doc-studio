import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
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
import { InboxPanel } from "@features/inbox";
import { TransferSection } from "@features/project-transfer";
import { ProjectInvitePage } from "@pages/ProjectInvitePage";
import { ProjectUnavailablePage } from "@pages/ProjectUnavailablePage";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";
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
    await user.type(within(form).getByTestId("invite-message"), "Привет");
    await user.click(screen.getByTestId("invite-submit"));
    const link = await screen.findByTestId("invite-link");
    expect(within(link).getByDisplayValue(/\/project-invite\//)).toBeTruthy();
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
