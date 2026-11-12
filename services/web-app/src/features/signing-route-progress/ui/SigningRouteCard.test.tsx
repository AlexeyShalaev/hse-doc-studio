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
  expectedTokens,
  signingTaskApi,
  type SigningRoute,
  type SigningRoutePreview,
} from "@entities/signing-route";
import {
  SR_AUTHOR,
  SR_PROJECT_ID,
  SR_SUPERVISOR,
  createSigningRouteDemo,
  makeRouteParticipant,
  makeSigningRoute,
  makeSigningRouteSummary,
  SIGNING_ROUTE_CONTRACT_EXAMPLES,
  type SigningDemoUser,
} from "@entities/signing-route/testing";
import { formatDay, formatMoment } from "../lib/format";
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

/**
 * Маршрут с прода: три обязательных слота ЭП и необязательный «Академический руководитель». Автор
 * согласовал отправкой и ждёт фиксации PDF, научрук и консультант согласуют параллельно.
 */
const approvedAuthorRoute = ({ optional = true } = {}): SigningRoute => {
  const slot = (id: string, participant: string | null, opt = false) => ({
    slot_id: id,
    label: { ru: id },
    participant_id: participant,
    extra: opt,
    optional: false,
    status: "pending" as const,
  });
  const esign = (id: string, slotId: string) =>
    makeRouteParticipant({
      id,
      persona: slotId,
      user_id: `u_${slotId}`,
      name: slotId,
      card_name: slotId,
      assignments: [{ doc_id: DOC, slot_id: slotId }],
      method: "detached",
      state: "to_approve_sign",
      next_action: "approve_and_sign",
      approved_at: null,
    });
  return makeSigningRoute({
    phase: "approval",
    docs: [
      {
        doc_id: DOC,
        name: { ru: "Заявление" },
        frozen: false,
        slots: [
          slot("author", "srp_author"),
          slot("supervisor", "srp_sup"),
          slot("consultant", "srp_cons"),
          ...(optional ? [slot("academic_supervisor", null, true)] : []),
        ],
        sent: null,
        changed: false,
      },
    ],
    steps: [
      [
        makeRouteParticipant({
          method: "detached",
          state: "waiting",
          next_action: "wait",
        }),
      ],
      [esign("srp_sup", "supervisor"), esign("srp_cons", "consultant")],
    ],
  });
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
      /^Шаг 2 из 2\. Очередь: Научный руководитель Петров П\. П\., с \d\d\.\d\dСогласовано 1 из 2 · подписано 1 из 2$/,
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
  it("версию на подписи подменили: причина и новая версия из рабочей сборки", async () => {
    await startRoute();
    demo.tamper(PROJECT, DOC);
    const u = userEvent.setup();
    mount();
    expect(await status()).toHaveTextContent(
      "Версия на подписи изменилась вне маршрута: маршрут остановлен.",
    );
    expect(screen.queryByTestId("signing-resend")).toBeNull();
    await u.click(screen.getByTestId("signing-new-version"));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    await u.click(within(dialog).getByTestId("signing-new-version-confirm"));
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
      card_name: null,
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
      "Очередь: Академический руководитель k***@hse.ru",
    );
    expect(await person(invited.id)).toHaveTextContent(
      "приглашение не принято",
    );
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

  it("приглашённый назван по карточке проекта, маска почты только подсказка", async () => {
    serveInvited(invitedPerson({ card_name: "Салех Х. М." }));
    mount({ projectId: SR_PROJECT_ID });
    const row = await person("srp_academic");
    expect(row).toHaveTextContent("Салех Х. М.");
    expect(
      screen.getByTestId("signing-person-hint-srp_academic"),
    ).toHaveTextContent("k***@hse.ru");
    expect(await status()).toHaveTextContent(
      "Очередь: Академический руководитель Салех Х. М.",
    );
  });

  it("автор согласовал раньше: когда попросят ЭП и кто не принял приглашение", async () => {
    // Случай с сервера: автор с открепленной ЭП согласовал при отправке, научрук и академрук
    // (картинки) ещё не приняли приглашение, почты на сервере нет.
    const supervisor = invitedPerson({
      id: "srp_supervisor",
      persona: "supervisor",
      name: "h***@hse.ru",
      card_name: "Салех Х. М.",
      changes_visible: true,
      assignments: [{ doc_id: "topic_application", slot_id: "supervisor" }],
      method: "image",
    });
    const academic = invitedPerson({
      changes_visible: true,
      name: "s***@hse.ru",
      card_name: null,
      method: "image",
    });
    serve(
      makeSigningRoute({
        phase: "approval",
        current_step: 2,
        steps: [
          [
            makeRouteParticipant({
              method: "detached",
              state: "waiting",
              next_action: "wait",
            }),
          ],
          [supervisor],
          [academic],
        ],
      }),
    );
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(
      bootstrap("server", { id: SR_AUTHOR.id, name: SR_AUTHOR.name }),
    );
    mount({ projectId: SR_PROJECT_ID });
    expect(
      await screen.findByTestId("signing-my-wait", {}, LOAD),
    ).toHaveTextContent(
      "Вы уже согласовали. Электронную подпись Студия попросит поставить после фиксации PDF, когда согласуют: Научный руководитель Салех Х. М. (шаг 2 из 3, приглашение не принято), Академический руководитель s***@hse.ru (шаг 3 из 3, приглашение не принято).",
    );
    expect(screen.getByTestId("signing-invited")).toHaveTextContent(
      "Не приняли приглашение в проект: Научный руководитель Салех Х. М., Академический руководитель s***@hse.ru. Сервер не отправляет письма: нажмите «Скопировать ссылку» рядом с человеком и перешлите её сами.",
    );
    // У приглашённых ссылка есть, у себя нет: свою страницу открывают кнопкой карточки.
    expect(screen.getByTestId("signing-copy-srp_supervisor")).toBeEnabled();
    expect(screen.getByTestId("signing-copy-srp_academic")).toBeEnabled();
    expect(screen.queryByTestId("signing-copy-srp_author")).toBeNull();
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
    expect(await status()).toHaveTextContent(
      "Согласовано 1 из 2 · подписано 1 из 2",
    );
  });

  it("автор согласовал отправкой, его ЭП ждёт фиксации: согласование видно отдельно", async () => {
    // Случай с прода: «Подписано 0 из 3» без согласований автор читал как ошибку.
    serve(approvedAuthorRoute());
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      "Согласовано 1 из 3 · подписано 0 из 3 + необязательная 0 из 1",
    );
  });

  it("без необязательных слотов хвоста нет; по-английски", async () => {
    await i18n.changeLanguage("en");
    serve(approvedAuthorRoute({ optional: false }));
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      /consultant1 of 3 approved · 0 of 3 signed · Due/,
    );
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    serve(makeSigningRoute());
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      /^Step 2 of 2\. Waiting for Supervisor Петров П\. П\., since/,
    );
    expect(screen.getByTestId("signing-cancel")).toHaveTextContent(
      "Cancel route",
    );
  });
});

const example = (name: string): SigningRoute =>
  SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoute?.[name] as SigningRoute;

describe("Подписание: версия на подписи (12.2)", () => {
  const today = () => formatDay(new Date().toISOString());

  it("у каждого документа версия на подписи и «Открыть версию на подписи»", async () => {
    await startRoute();
    mount();
    const row = await screen.findByTestId("signing-version", {}, LOAD);
    const route = await signingRouteApi.get(
      PROJECT,
      (await signingRouteApi.list(PROJECT, PROFILE)).items[0]?.id ?? "",
    );
    const sent = route.docs[0]?.sent?.at ?? "";
    expect(row).toHaveTextContent("Заявление о выборе темы");
    expect(row).toHaveTextContent(
      `Версия на подписи от ${formatMoment(Date.parse(sent))}`,
    );
    expect(row).toHaveAttribute("data-changed", "false");
    expect(within(row).getByTestId("signing-version-open")).toHaveAttribute(
      "href",
      expect.stringMatching(
        new RegExp(`/api/v1/projects/${PROJECT}/docs/${DOC}/pdf/signed$`),
      ),
    );
    // Изменений нет: отправлять нечего, маршрут идёт.
    expect(screen.queryByTestId("signing-changed")).toBeNull();
    expect(screen.queryByTestId("signing-new-version")).toBeNull();
    expect(screen.queryByTestId("signing-resend")).toBeNull();
  });

  it("пересобран после отправки: маршрут идёт, автор видит изменения и отправляет новую версию с пояснением", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    const send = vi.spyOn(signingRouteApi, "send");
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount();
    expect(await status()).toHaveAttribute("data-status", "active");
    expect(
      await screen.findByTestId("signing-changed", {}, LOAD),
    ).toHaveTextContent(
      `Есть изменения после отправки на подпись. Подписывают версию от ${today()}.`,
    );
    expect(screen.getByTestId("signing-version")).toHaveAttribute(
      "data-changed",
      "true",
    );
    expect(screen.getByTestId("signing-version")).toHaveTextContent(
      "есть изменения",
    );

    await u.click(screen.getByTestId("signing-new-version"));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    expect(dialog).toHaveTextContent("Отправить новую версию?");
    expect(
      within(dialog).getByTestId("signing-new-version-changed"),
    ).toHaveTextContent("Изменились: Заявление о выборе темы.");
    // Научрук ещё не согласовывал: заново согласовывать некому.
    expect(
      within(dialog).queryByTestId("signing-new-version-reapprove"),
    ).toBeNull();
    expect(within(dialog).queryByTestId("signing-new-version-kept")).toBeNull();
    await u.type(
      within(dialog).getByLabelText("Что изменилось"),
      "Исправил формулировку темы",
    );
    await u.click(within(dialog).getByTestId("signing-new-version-confirm"));
    await waitFor(() => {
      expect(screen.queryByTestId("signing-changed")).toBeNull();
    }, LOAD);
    expect(send.mock.calls[0]?.[2]).toMatchObject({
      sign: null,
      note: "Исправил формулировку темы",
    });
    expect(success).toHaveBeenCalledWith("Новая версия отправлена");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByTestId("signing-new-version")).toBeNull();
  });

  it("«Не отправлять» закрывает подтверждение без отправки", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    const send = vi.spyOn(signingRouteApi, "send");
    const u = userEvent.setup();
    mount();
    await u.click(await screen.findByTestId("signing-new-version", {}, LOAD));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    await u.click(
      within(dialog).getByRole("button", { name: "Не отправлять" }),
    );
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(send).not.toHaveBeenCalled();
  });

  it("согласовавший научрук в подтверждении: согласует заново", async () => {
    const id = await startRoute();
    user = PETROV;
    const task = await signingTaskApi.get(PROJECT, id);
    await signingTaskApi.approve(PROJECT, id, {
      expected: expectedTokens(task),
      method: null,
      sign: null,
    });
    user = AUTHOR;
    demo.rebuild(PROJECT, DOC);
    const u = userEvent.setup();
    mount();
    await u.click(await screen.findByTestId("signing-new-version", {}, LOAD));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    expect(
      within(dialog).getByTestId("signing-new-version-reapprove"),
    ).toHaveTextContent(/^Согласуют заново: .*Петров П\. П\.$/);
  });

  it("без изменений документы и подписи на них останутся", async () => {
    const route = example("diverged");
    const two: SigningRoute = {
      ...route,
      docs: [
        ...route.docs,
        {
          doc_id: "supervisor_review",
          name: { ru: "Отзыв руководителя", en: "Supervisor's review" },
          frozen: true,
          slots: [],
          sent: route.docs[0]?.sent ?? null,
          changed: false,
        },
      ],
    };
    serve(two);
    const preview = SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoutePreview
      ?.new_version as SigningRoutePreview;
    vi.spyOn(signingRouteApi, "preview").mockResolvedValue(preview);
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    expect(
      await screen.findAllByTestId("signing-version", {}, LOAD),
    ).toHaveLength(2);
    await u.click(screen.getByTestId("signing-new-version"));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    expect(
      within(dialog).getByTestId("signing-new-version-kept"),
    ).toHaveTextContent(
      "Без изменений: Отзыв руководителя, подписи на нём останутся.",
    );
  });

  it("изменения успели отправить: подтверждения нет, маршрут перечитан", async () => {
    serve(example("diverged"));
    vi.spyOn(signingRouteApi, "preview").mockResolvedValue({
      ...(SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoutePreview
        ?.new_version as SigningRoutePreview),
      can_send: false,
      blockers: [
        {
          code: "nothing_changed",
          doc_id: null,
          slot_id: null,
          participant_id: null,
          other_route: null,
        },
      ],
    });
    const info = vi.spyOn(toast, "info");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await u.click(await screen.findByTestId("signing-new-version", {}, LOAD));
    await waitFor(() => {
      expect(info).toHaveBeenCalledWith(
        "Изменений после отправки нет: отправлять нечего.",
      );
    }, LOAD);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("все подписали, потом правка: «Есть изменения после подписания» и новая версия", async () => {
    serve(example("completed_changed"));
    mount({ projectId: SR_PROJECT_ID });
    const day = formatDay("2026-11-10T09:00:00Z");
    expect(await status()).toHaveTextContent(`Все подписали версию от ${day}.`);
    expect(screen.getByTestId("signing-changed")).toHaveTextContent(
      "Есть изменения после подписания.",
    );
    expect(screen.getByTestId("signing-new-version")).toBeInTheDocument();
    expect(screen.getByTestId("signing-archive")).toBeInTheDocument();
  });

  it("перенос 0.20.0 не нашёл версию: восстановить нельзя, отправьте новую", async () => {
    serve(example("migration_lost"));
    mount({ projectId: SR_PROJECT_ID });
    expect(await status()).toHaveTextContent(
      "Версию, отправленную на подпись, восстановить нельзя: отправьте новую версию.",
    );
    expect(screen.queryByTestId("signing-changed")).toBeNull();
    const row = screen.getByTestId("signing-version");
    expect(row).toHaveTextContent("Версии на подписи нет");
    expect(within(row).queryByTestId("signing-version-open")).toBeNull();
    expect(screen.getByTestId("signing-new-version")).toBeInTheDocument();
    expect(screen.queryByTestId("signing-resend")).toBeNull();
  });

  it("читателю версия видна, а изменения и новая версия нет", async () => {
    serve(example("diverged"));
    mount({ projectId: SR_PROJECT_ID, role: "reviewer" });
    const row = await screen.findByTestId("signing-version", {}, LOAD);
    expect(row).toHaveAttribute("data-changed", "false");
    expect(screen.queryByTestId("signing-changed")).toBeNull();
    expect(screen.queryByTestId("signing-new-version")).toBeNull();
  });

  it("версии на подписи нет: ни версий, ни изменений", async () => {
    const route = makeSigningRoute();
    serve({
      ...route,
      docs: route.docs.map((doc) => ({ ...doc, sent: null })),
    });
    mount({ projectId: SR_PROJECT_ID });
    await status();
    expect(screen.queryByTestId("signing-versions")).toBeNull();
    expect(screen.queryByTestId("signing-changed")).toBeNull();
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    serve(example("diverged"));
    mount({ projectId: SR_PROJECT_ID });
    expect(
      await screen.findByTestId("signing-changed", {}, LOAD),
    ).toHaveTextContent(
      `There are changes since it was sent for signing. Signers sign the version from ${formatDay("2026-11-10T09:00:00Z")}.`,
    );
    expect(screen.getByTestId("signing-new-version")).toHaveTextContent(
      "Send new version",
    );
    expect(screen.getByTestId("signing-version-open")).toHaveTextContent(
      "Open the version for signing",
    );
  });
});

describe("пропустить подписанта (13.9)", () => {
  const example = (name: string) =>
    SIGNING_ROUTE_CONTRACT_EXAMPLES.SigningRoute?.[name] as SigningRoute;
  const academic = (route: SigningRoute) =>
    route.steps.flat().find((p) => p.id === "srp_academic")!;

  it("у очереди с необязательными подписями подсказка и кнопка, подтверждение называет перефиксацию", async () => {
    const route = example("skippable_refreezes");
    serve(route);
    const skip = vi
      .spyOn(signingRouteApi, "skip")
      .mockResolvedValue(example("skipped"));
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    expect(
      screen.getByTestId("signing-skip-hint-srp_academic"),
    ).toHaveTextContent(
      "Все подписи этого человека на точке необязательны. Его можно пропустить",
    );
    // У научрука обязательная подпись: кнопки нет.
    expect(screen.queryByTestId("signing-skip-srp_supervisor")).toBeNull();
    await u.click(screen.getByTestId("signing-skip-srp_academic"));
    const lines = await screen.findByTestId("signing-skip-lines");
    expect(lines).toHaveTextContent("Место подписи останется пустым");
    expect(lines).toHaveTextContent("будет зафиксирован заново без этой метки");
    expect(lines).toHaveTextContent(
      "получит уведомление, что подпись не требуется",
    );
    expect(lines).not.toHaveTextContent("останется в нём");
    await u.click(screen.getByTestId("signing-skip-confirm"));
    await waitFor(() => {
      expect(skip).toHaveBeenCalledWith(
        route.project_id,
        route.id,
        "srp_academic",
      );
    });
    expect(success).toHaveBeenCalled();
  });

  it("если над документом уже есть ЭП, подтверждение говорит, что метка останется", async () => {
    serve(example("skippable_keeps_marks"));
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    await u.click(screen.getByTestId("signing-skip-srp_academic"));
    const lines = await screen.findByTestId("signing-skip-lines");
    expect(lines).toHaveTextContent("уже стоит в зафиксированном PDF");
    expect(lines).toHaveTextContent("останется в нём");
    expect(lines).not.toHaveTextContent("будет зафиксирован заново");
  });

  it("«Не пропускать» ничего не отправляет", async () => {
    serve(example("skippable"));
    const skip = vi.spyOn(signingRouteApi, "skip");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    await u.click(screen.getByTestId("signing-skip-srp_academic"));
    await u.click(await screen.findByRole("button", { name: "Не пропускать" }));
    expect(skip).not.toHaveBeenCalled();
  });

  it("пропущенный в шагах: «подпись не требуется, пропущено» с датой", async () => {
    const route = example("skipped");
    serve(route);
    mount({ projectId: SR_PROJECT_ID });
    const row = await person("srp_academic");
    expect(row).toHaveAttribute("data-state", "skipped");
    expect(row).toHaveTextContent(
      `подпись не требуется, пропущено ${formatDay(academic(route).skipped_at!)}`,
    );
    expect(screen.queryByTestId("signing-skip-srp_academic")).toBeNull();
  });

  it("если отметку сняли после пропуска, пишет, что человек вернётся в маршрут", async () => {
    const route = example("skipped");
    const back = {
      ...route,
      docs: route.docs.map((doc) => ({
        ...doc,
        slots: doc.slots.map((slot) =>
          slot.status === "skipped" ? { ...slot, optional: false } : slot,
        ),
      })),
    };
    serve(back);
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    expect(
      screen.getByTestId("signing-skip-returns-srp_academic"),
    ).toHaveTextContent("Вернётся в маршрут при следующей отправке");
  });

  it("если у человека есть необязательная подпись, но очередь не его, пишет причину", async () => {
    const route = example("skippable");
    const waiting = {
      ...route,
      steps: route.steps.map((step) =>
        step.map((p) =>
          p.id === "srp_academic"
            ? {
                ...p,
                skip: {
                  ...p.skip!,
                  available: false,
                  blocker: "not_turn" as const,
                },
              }
            : p,
        ),
      ),
    };
    serve(waiting);
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    expect(screen.queryByTestId("signing-skip-srp_academic")).toBeNull();
    expect(
      screen.getByTestId("signing-skip-blocker-srp_academic"),
    ).toHaveTextContent("Пропустить можно, когда дойдёт его очередь");
  });

  it("отказ 409 показывает причину из ответа", async () => {
    serve(example("skippable"));
    vi.spyOn(signingRouteApi, "skip").mockRejectedValue(
      new ApiError("no", "participant_not_skippable", 409, {
        reason: "required_slots",
      }),
    );
    const error = vi.spyOn(toast, "error");
    const u = userEvent.setup();
    mount({ projectId: SR_PROJECT_ID });
    await person("srp_academic");
    await u.click(screen.getByTestId("signing-skip-srp_academic"));
    await u.click(await screen.findByTestId("signing-skip-confirm"));
    await waitFor(() => {
      expect(error).toHaveBeenCalledWith(
        "Есть обязательные подписи: пропустить нельзя",
      );
    });
  });

  it("читателю кнопки нет", async () => {
    serve(example("skippable"));
    mount({ role: "reader", projectId: SR_PROJECT_ID });
    await person("srp_academic");
    expect(screen.queryByTestId("signing-skip-srp_academic")).toBeNull();
  });
});
