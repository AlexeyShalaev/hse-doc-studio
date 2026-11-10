import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router";
import type { z } from "zod";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { ApiError, apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { i18n, toast } from "@shared/lib";
import type { ProjectResponseSchema } from "@entities/project";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import {
  signingRouteApi,
  signingTaskApi,
  type SigningRoute,
} from "@entities/signing-route";
import {
  SR_AUTHOR,
  SR_PROJECT_ID,
  SR_SUPERVISOR,
  createSigningRouteDemo,
  makeRouteParticipant,
  makeSigningRoute,
  makeSigningRouteSummary,
  type SigningDemoUser,
} from "@entities/signing-route/testing";
import { SigningRouteCard } from "./SigningRouteCard";

type Project = z.infer<typeof ProjectResponseSchema>;
type Role = "owner" | "editor" | "reviewer" | "reader";

const PROJECT = "p_demo";
const PROFILE = "topic-approval";
const DOC = "topic_application";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const PETROV: SigningDemoUser = { id: "u_demo_petrov", name: "Петров П. П." };

let user: SigningDemoUser = AUTHOR;
const demo = createSigningRouteDemo({ getUser: () => user });

const bootstrap = (
  mode: "server" | "local",
  who: SigningDemoUser = AUTHOR,
) => ({
  ...LOCAL_BOOTSTRAP,
  mode,
  user: {
    id: who.id,
    name: who.name,
    email: "user@edu.hse.ru",
    avatar_initials: "ИИ",
    is_instance_admin: false,
    email_verified: true,
    locale: null,
    org_roles: [],
  },
});

const mount = ({
  role = "owner",
  projectId = PROJECT,
  signatures = { done: 0, total: 3 },
}: {
  role?: Role;
  projectId?: string;
  signatures?: { done: number; total: number };
} = {}) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const project = {
    id: projectId,
    authors: [],
    lang: "ru",
    my_role: role,
  } as unknown as Project;
  const point = `/projects/${projectId}/submit/cp/${PROFILE}`;
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[point]}>
          <Routes>
            <Route
              path={point}
              element={
                <SigningRouteCard
                  project={project}
                  profileId={PROFILE}
                  signatures={signatures}
                />
              }
            />
            <Route path={`${point}/route`} element={<p>editor</p>} />
            <Route path="/sign/:projectId/:routeId" element={<p>sign</p>} />
            <Route
              path="/projects/:projectId/documents/:docId"
              element={<p>document</p>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
};

/** Отправить маршрут точки от автора, как это делает экран W2. */
const startRoute = async (): Promise<string> => {
  const route = await signingRouteApi.create(PROJECT, PROFILE);
  const preview = await signingRouteApi.preview(PROJECT, route.id);
  await signingRouteApi.send(PROJECT, route.id, {
    expected: Object.fromEntries(
      preview.docs.map((doc) => [doc.doc_id, doc.token ?? ""]),
    ),
    sign: null,
  });
  return route.id;
};

// Сессия, список и ход маршрута идут друг за другом: под нагрузкой это дольше секунды.
const LOAD = { timeout: 5000 };
const status = () => screen.findByTestId("signing-status", {}, LOAD);
const person = (id: string) =>
  screen.findByTestId(`signing-person-${id}`, {}, LOAD);

/** Ответы сервера из эталонов: состояние, которого демо не даёт само. */
const serve = (route: SigningRoute) => {
  vi.spyOn(signingRouteApi, "list").mockResolvedValue({
    items: [
      makeSigningRouteSummary({
        id: route.id,
        status: route.status,
        current_step: route.current_step,
      }),
    ],
  });
  vi.spyOn(signingRouteApi, "get").mockResolvedValue(route);
};

beforeAll(() => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
});

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  demo.reset();
  user = AUTHOR;
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("server"));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Подписание: маршрута нет", () => {
  it("счёт подписей точки и «Отправить на подписание» ведёт в редактор", async () => {
    const u = userEvent.setup();
    mount();
    const card = await screen.findByTestId("signing-card", {}, LOAD);
    expect(card).toHaveTextContent("Подписано 0 из 3");
    expect(card).toHaveTextContent("руководители подпишут у себя");
    await u.click(screen.getByTestId("signing-send"));
    expect(await screen.findByText("editor")).toBeInTheDocument();
  });

  it("читателю и точке без подписей карточка не нужна", async () => {
    const list = vi.spyOn(signingRouteApi, "list");
    mount({ role: "reviewer" });
    await waitFor(() => {
      expect(list).toHaveBeenCalled();
    }, LOAD);
    expect(screen.queryByTestId("signing-card")).toBeNull();
  });

  it("гость по ссылке: маршруты не спрашиваем", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
      ...bootstrap("server"),
      user: null,
    });
    const list = vi.spyOn(signingRouteApi, "list");
    mount({ role: "reader" });
    await waitFor(() => {
      expect(sessionApi.bootstrap).toHaveBeenCalled();
    }, LOAD);
    expect(screen.queryByTestId("signing-card")).toBeNull();
    expect(list).not.toHaveBeenCalled();
  });

  it("локальная Студия: маршрутов нет, карточки нет", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("local"));
    const list = vi.spyOn(signingRouteApi, "list");
    mount();
    await waitFor(() => {
      expect(sessionApi.bootstrap).toHaveBeenCalled();
    }, LOAD);
    expect(screen.queryByTestId("signing-card")).toBeNull();
    expect(list).not.toHaveBeenCalled();
  });
});

describe("Подписание: маршрут идёт", () => {
  it("шаг, чья очередь и ход по шагам", async () => {
    const id = await startRoute();
    mount();
    expect(await status()).toHaveTextContent(
      /^Шаг 2 из 2\. Очередь: Петров П\. П\. \(научный руководитель\), с \d\d\.\d\dПодписано 1 из 2$/,
    );
    expect(await screen.findByTestId("signing-step-2")).toHaveAttribute(
      "data-current",
      "true",
    );
    const author = within(await screen.findByTestId("signing-step-1"));
    expect(author.getByText("Иванов И. И.")).toBeInTheDocument();
    expect(author.getByText(/^подписано/)).toBeInTheDocument();
    const step2 = await screen.findByTestId("signing-step-2");
    expect(step2).toHaveTextContent("согласует и подпишет с");
    // Автор уже всё сделал: напоминать ему нечего.
    const route = await signingRouteApi.get(PROJECT, id);
    const first = route.steps[0]?.[0]?.id ?? "";
    expect(screen.queryByTestId(`signing-remind-${first}`)).toBeNull();
    expect(screen.getByTestId("signing-cancel")).toBeInTheDocument();
    expect(screen.queryByTestId("signing-resend")).toBeNull();
  });

  it("«Напомнить» раз в 12 часов", async () => {
    const id = await startRoute();
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount();
    const route = await signingRouteApi.get(PROJECT, id);
    const sup = route.steps[1]?.[0]?.id ?? "";
    await u.click(await screen.findByTestId(`signing-remind-${sup}`, {}, LOAD));
    await waitFor(() => {
      expect(success).toHaveBeenCalledWith(
        "Напоминание отправлено во «Входящие»",
      );
    }, LOAD);
    await waitFor(() => {
      expect(screen.getByTestId(`signing-remind-${sup}`)).toBeDisabled();
    }, LOAD);
    expect(
      screen.getByTestId(`signing-remind-${sup}`).parentElement,
    ).toHaveAttribute("title", expect.stringMatching(/^Напомнить можно после/));
    // Ссылку участнику копировать можно и после напоминания.
    expect(screen.getByTestId(`signing-copy-${sup}`)).toBeEnabled();
  });

  it("«Скопировать ссылку»: адрес страницы подписи в буфер", async () => {
    const id = await startRoute();
    const u = userEvent.setup();
    mount();
    const route = await signingRouteApi.get(PROJECT, id);
    const sup = route.steps[1]?.[0]?.id ?? "";
    await u.click(await screen.findByTestId(`signing-copy-${sup}`, {}, LOAD));
    await waitFor(async () => {
      expect(await navigator.clipboard.readText()).toBe(
        `${window.location.origin}/sign/${PROJECT}/${id}`,
      );
    }, LOAD);
  });

  it("буфер недоступен: ссылка видна под человеком", async () => {
    const id = await startRoute();
    const u = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new Error("denied"),
    );
    mount();
    const route = await signingRouteApi.get(PROJECT, id);
    const sup = route.steps[1]?.[0]?.id ?? "";
    await u.click(await screen.findByTestId(`signing-copy-${sup}`, {}, LOAD));
    expect(
      await screen.findByDisplayValue(
        `${window.location.origin}/sign/${PROJECT}/${id}`,
      ),
    ).toBeInTheDocument();
  });

  it("«Отменить маршрут» спрашивает и отменяет", async () => {
    await startRoute();
    const u = userEvent.setup();
    mount();
    await u.click(await screen.findByTestId("signing-cancel", {}, LOAD));
    expect(await screen.findByText("Отменить маршрут?")).toBeInTheDocument();
    await u.click(screen.getByTestId("signing-cancel-confirm"));
    await waitFor(async () => {
      expect(await status()).toHaveTextContent("Маршрут отменён.");
    }, LOAD);
    expect(screen.getByTestId("signing-resend")).toBeInTheDocument();
    expect(screen.queryByTestId("signing-cancel")).toBeNull();
  });
});

describe("Подписание: остановка и возврат", () => {
  it("документ пересобран: причина и «Отправить заново» одним нажатием", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    const u = userEvent.setup();
    mount();
    expect(await status()).toHaveTextContent(
      "Документ изменился после согласования: маршрут остановлен.",
    );
    await u.click(screen.getByTestId("signing-resend"));
    await waitFor(async () => {
      expect(await status()).toHaveAttribute("data-status", "active");
    }, LOAD);
    expect(await status()).toHaveTextContent(/^Шаг 2 из 2/);
  });

  it("вернули на доработку: кто, комментарий, документ и повторная отправка", async () => {
    const id = await startRoute();
    user = PETROV;
    await signingTaskApi.returnForRework(PROJECT, id, {
      comment: "Уточните цель проекта",
    });
    user = AUTHOR;
    const u = userEvent.setup();
    mount();
    expect(await status()).toHaveTextContent(
      "Возвращено на доработку (Петров П. П.): «Уточните цель проекта»",
    );
    const route = await signingRouteApi.get(PROJECT, id);
    const sup = route.steps[1]?.[0]?.id ?? "";
    expect(await person(sup)).toHaveTextContent("возвращено на доработку");
    expect(screen.getByTestId("signing-open-doc")).toHaveAttribute(
      "href",
      `/projects/${PROJECT}/documents/${DOC}`,
    );
    await u.click(screen.getByTestId("signing-resend"));
    await waitFor(async () => {
      expect(await status()).toHaveAttribute("data-status", "active");
    }, LOAD);
  });

  it("отправить нельзя: ведёт в редактор маршрута", async () => {
    const route = makeSigningRoute({
      status: "paused",
      phase: null,
      current_step: null,
      stop_reason: "participant_left",
    });
    serve(route);
    vi.spyOn(signingRouteApi, "preview").mockResolvedValue({
      route_id: route.id,
      can_send: false,
      can_send_and_sign: false,
      visual_step: 0,
      docs: [],
      participants: [],
      blockers: [
        {
          code: "participant_missing",
          doc_id: null,
          slot_id: null,
          participant_id: "srp_supervisor",
          other_route: null,
        },
      ],
      sender_key: null,
    });
    const send = vi.spyOn(signingRouteApi, "send");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      "Участник ушёл из проекта: назначьте другого и отправьте заново.",
    );
    await u.click(screen.getByTestId("signing-resend"));
    expect(await screen.findByText("editor")).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });
});

describe("Подписание: эталонные состояния", () => {
  const invitedPerson = (
    overrides: Partial<SigningRoute["steps"][0][0]> = {},
  ) =>
    makeRouteParticipant({
      id: "srp_academic",
      persona: "academic_supervisor",
      user_id: null,
      invitation_id: "pinv_1",
      name: "k***@hse.ru",
      membership: "invited",
      assignments: [{ doc_id: "topic_application", slot_id: "academic" }],
      state: "invited",
      next_action: "wait",
      approved_at: null,
      ...overrides,
    });
  const serveInvited = (invited: SigningRoute["steps"][0][0]) => {
    serve(
      makeSigningRoute({
        current_step: 2,
        steps: [[makeRouteParticipant()], [invited]],
      }),
    );
  };

  it("приглашённому «Скопировать ссылку» берёт ссылку приглашения без напоминания и его паузы", async () => {
    // Приглашён только что: «Напомнить» по правилу 12 часов было бы закрыто, но почты на
    // сервере нет, и обе кнопки отдают ссылку.
    const invited = invitedPerson({ reminded_at: new Date().toISOString() });
    serveInvited(invited);
    const link = "https://studio.example.org/project-invite/hspi_x";
    const getLink = vi.spyOn(signingRouteApi, "link").mockResolvedValue({
      participant_id: invited.id,
      kind: "invitation",
      link,
    });
    const remind = vi.spyOn(signingRouteApi, "remind");
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      "Очередь: k***@hse.ru (академический руководитель)",
    );
    expect(await person(invited.id)).toHaveTextContent("приглашение не принято");
    expect(screen.getByTestId(`signing-remind-${invited.id}`)).toBeEnabled();
    await u.click(screen.getByTestId(`signing-copy-${invited.id}`));
    await waitFor(async () => {
      expect(await navigator.clipboard.readText()).toBe(link);
    }, LOAD);
    expect(getLink).toHaveBeenCalledWith(
      SR_PROJECT_ID,
      expect.any(String),
      invited.id,
    );
    expect(remind).not.toHaveBeenCalled();
    expect(success).toHaveBeenCalledWith(
      "Ссылка-приглашение скопирована: отправьте её сами",
    );
  });

  it("«Скопировать ссылку» и у того, чья очередь ещё не дошла: ссылку можно разослать заранее", async () => {
    const later = makeRouteParticipant({
      id: "srp_academic",
      persona: "academic_supervisor",
      user_id: "u_academic",
      name: "Сидоров С. С.",
      assignments: [{ doc_id: "topic_application", slot_id: "academic" }],
      state: "waiting",
      next_action: "wait",
      approved_at: null,
    });
    serve(
      makeSigningRoute({
        current_step: 2,
        steps: [
          [makeRouteParticipant()],
          [
            makeRouteParticipant({
              id: "srp_supervisor",
              persona: "supervisor",
              user_id: SR_SUPERVISOR.id,
              name: SR_SUPERVISOR.name,
              state: "to_approve",
              next_action: "approve",
              approved_at: null,
            }),
          ],
          [later],
        ],
      }),
    );
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    expect(await person(later.id)).toHaveTextContent("ждёт");
    // Напоминать ему рано, а ссылку на его страницу подписи отправить уже можно.
    expect(screen.queryByTestId(`signing-remind-${later.id}`)).toBeNull();
    await u.click(screen.getByTestId(`signing-copy-${later.id}`));
    await waitFor(async () => {
      expect(await navigator.clipboard.readText()).toMatch(
        new RegExp(`/sign/${SR_PROJECT_ID}/[^/]+$`),
      );
    }, LOAD);
    // Тому, кто уже всё сделал, ссылка не нужна.
    expect(screen.queryByTestId("signing-copy-srp_author")).toBeNull();
  });

  it("приглашённый без имени назван приглашённым, а не «не назначен»", async () => {
    serveInvited(invitedPerson({ name: null }));
    mount({ projectId: SR_PROJECT_ID });
    expect(await person("srp_academic")).toHaveTextContent("Приглашённый");
    expect(
      screen.getByTestId("signing-person-srp_academic"),
    ).not.toHaveTextContent("Не назначен");
  });

  it("с почтой на сервере ссылку несёт письмо: копировать нечего, «Напомнить» раз в 12 часов", async () => {
    const boot = bootstrap("server");
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
      ...boot,
      auth: { ...boot.auth, smtp_enabled: true },
    });
    const invited = invitedPerson({ reminded_at: new Date().toISOString() });
    serveInvited(invited);
    mount({ projectId: SR_PROJECT_ID });
    await person(invited.id);
    expect(screen.queryByTestId(`signing-copy-${invited.id}`)).toBeNull();
    expect(screen.getByTestId(`signing-remind-${invited.id}`)).toBeDisabled();
  });

  it("сервер не дал ссылку приглашения: причина в тосте", async () => {
    const invited = invitedPerson();
    serveInvited(invited);
    vi.spyOn(signingRouteApi, "link").mockRejectedValue(
      new ApiError("by mail", "link_by_mail", 409),
    );
    const failure = vi.spyOn(toast, "error");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await u.click(
      await screen.findByTestId(`signing-copy-${invited.id}`, {}, LOAD),
    );
    await waitFor(() => {
      expect(failure).toHaveBeenCalledWith(
        "Ссылка приглашения уходит письмом. Чтобы отправить его ещё раз, нажмите «Напомнить».",
      );
    }, LOAD);
  });

  it("отправитель ещё не подписал сам: «подпись не поставлена» и переход к подписи", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(
      bootstrap("server", SR_AUTHOR),
    );
    const route = makeSigningRoute({
      current_step: 1,
      steps: [
        [
          makeRouteParticipant({
            method: "detached",
            state: "to_sign",
            next_action: "sign",
          }),
        ],
      ],
    });
    serve(route);
    mount({ projectId: SR_PROJECT_ID });
    expect(
      await screen.findByTestId("signing-unsigned", {}, LOAD),
    ).toHaveTextContent("Маршрут отправлен, ваша подпись ещё не поставлена.");
    expect(screen.getByTestId("signing-go")).toHaveAttribute(
      "href",
      `/sign/${SR_PROJECT_ID}/${route.id}`,
    );
  });

  it("подписанту, который не отправлял маршрут, про «не поставлена» не пишем", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(
      bootstrap("server", SR_SUPERVISOR),
    );
    serve(makeSigningRoute());
    mount({ projectId: SR_PROJECT_ID, role: "reviewer" });
    await screen.findByTestId("signing-go", {}, LOAD);
    expect(screen.queryByTestId("signing-unsigned")).toBeNull();
  });

  it("завершён: «Все подписали», снять с контроля", async () => {
    const route = makeSigningRoute({
      status: "completed",
      phase: "done",
      current_step: null,
      completed_at: "2026-11-11T10:00:00Z",
    });
    serve(route);
    const archive = vi
      .spyOn(signingRouteApi, "archive")
      .mockResolvedValue({ ...route, status: "archived" });
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      "Все подписали. Можно собирать пакет.",
    );
    expect(screen.queryByTestId("signing-cancel")).toBeNull();
    await u.click(screen.getByTestId("signing-archive"));
    await waitFor(() => {
      expect(archive).toHaveBeenCalledWith(SR_PROJECT_ID, route.id);
    }, LOAD);
  });

  it("подписант в свою очередь: «Перейти к подписи», без действий автора", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(
      bootstrap("server", SR_SUPERVISOR),
    );
    const route = makeSigningRoute();
    serve(route);
    mount({ projectId: SR_PROJECT_ID, role: "reviewer" });
    expect(await screen.findByTestId("signing-go", {}, LOAD)).toHaveAttribute(
      "href",
      `/sign/${SR_PROJECT_ID}/${route.id}`,
    );
    expect(await person("srp_supervisor")).toHaveTextContent("вы");
    expect(screen.queryByTestId("signing-remind-srp_supervisor")).toBeNull();
    expect(screen.queryByTestId("signing-cancel")).toBeNull();
    expect(screen.queryByTestId("signing-open")).toBeNull();
  });

  it("срок прошёл: помечен, маршрут идёт", async () => {
    serve(makeSigningRoute({ deadline: "2020-01-01T00:00:00Z" }));
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent("Срок прошёл 01.01");
    expect(await status()).toHaveTextContent("Подписано 1 из 2");
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    serve(makeSigningRoute());
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      /^Step 2 of 2\. Waiting for Петров П\. П\. \(supervisor\), since/,
    );
    expect(screen.getByTestId("signing-cancel")).toHaveTextContent(
      "Cancel route",
    );
  });
});
