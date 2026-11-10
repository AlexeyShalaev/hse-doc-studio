import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
import { i18n } from "@shared/lib";
import { documentApi } from "@entities/document";
import {
  projectInvitationsApi,
  type ProjectInvitation,
} from "@entities/invitation";
import { projectApi, type ProjectResponseSchema } from "@entities/project";
import { buildAvailabilityApi } from "@entities/runner";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import { signingRouteApi } from "@entities/signing-route";
import {
  createSigningRouteDemo,
  type SigningDemoUser,
} from "@entities/signing-route/testing";
import { SigningRouteEditor } from "./SigningRouteEditor";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

// Предпросмотр PDF не нужен: проверяем, какие слоты экран отдаёт редактору размещения.
vi.mock("@features/signature-stamper", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  PdfStampEditor: ({ slotDefs }: { slotDefs: readonly { id: string }[] }) => (
    <div data-testid="stamp-editor">{slotDefs.map((s) => s.id).join(",")}</div>
  ),
}));

type Project = z.infer<typeof ProjectResponseSchema>;

const PROJECT = "p_demo";
const PROFILE = "topic-approval";
const DOC = "topic_application";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const PATH = `/projects/${PROJECT}/submit/cp/${PROFILE}`;

// Места слотов на странице: демо маршрута и подписи проекта смотрят в один набор.
let unplaced = new Set<string>();
const demo = createSigningRouteDemo({
  getUser: () => AUTHOR,
  // Два научрука в проекте: автор выбирает, кто подписывает.
  members: [
    {
      user_id: "u_demo_petrov",
      name: "Петров П. П.",
      persona: "supervisor",
      plate: { owner: "Петров П. П.", kind: "openpgp", cert_id: "1A2B" },
    },
    {
      user_id: "u_demo_sidorova",
      name: "Сидорова А. В.",
      persona: "supervisor",
      plate: null,
    },
  ],
  invitations: [
    { invitation_id: "inv_co", persona: "co_supervisor", hint: "c***@hse.ru" },
  ],
  isPlaced: (_project, _doc, slot) => !unplaced.has(slot),
});

/** Все подписывают ЭП с известными данными плашки: «Отправить и подписать» ключом с паролем. */
const cryptoDemo = createSigningRouteDemo({
  getUser: () => AUTHOR,
  members: [
    {
      user_id: AUTHOR.id,
      name: AUTHOR.name,
      persona: "author_key",
      plate: { owner: AUTHOR.name, kind: "openpgp", cert_id: "3C4D" },
    },
    {
      user_id: "u_demo_petrov",
      name: "Петров П. П.",
      persona: "supervisor",
      plate: { owner: "Петров П. П.", kind: "openpgp", cert_id: "1A2B" },
    },
  ],
  profiles: [
    {
      id: PROFILE,
      name: { ru: "Заявка на тему КП", en: "Topic application" },
      order: [["author"], ["supervisor"]],
      docs: [
        {
          doc_id: DOC,
          name: { ru: "Заявление о выборе темы", en: "Topic application" },
          slots: ["author", "supervisor"].map((persona, i) => ({
            slot_id: persona,
            label: { ru: persona, en: persona },
            persona,
            method: "detached" as const,
            optional: false,
            page: 1,
            x_mm: 100,
            y_mm: 100 + i * 30,
            width_mm: 60,
          })),
        },
      ],
    },
  ],
  keysOf: (user) => [
    {
      id: `key-${user.id}`,
      label: "Ключ OpenPGP",
      kind: "openpgp",
      protected: true,
      signer: user.name,
    },
  ],
});

const invitation = (id: string, persona: string): ProjectInvitation => ({
  id,
  invitee: {
    kind: "email",
    user_id: null,
    name: null,
    email_hint: "c***@hse.ru",
  },
  role: "reviewer",
  persona,
  can_share: false,
  show_sources: true,
  can_edit_all: false,
  message: null,
  invited_by: null,
  created_at: "2026-11-09T10:00:00Z",
  expires_at: "2026-11-16T10:00:00Z",
  status: "pending",
  sent_count: 1,
  last_sent_at: "2026-11-09T10:00:00Z",
});

const slotDef = (id: string, ru: string) => ({
  id,
  label: { ru, en: ru },
  applies_to: [DOC],
  required_by: {},
  default_placement: { page: 1, x_mm: 100, y_mm: 200, width_mm: 40 },
  owner: null,
});

const placement = (enabled: boolean) => ({
  enabled,
  page: 1,
  x_mm: 100,
  y_mm: 200,
  width_mm: 40,
  sign_date: null,
});

const slotInfo = (mode: "image" | "detached_text") => ({
  png_path: null,
  natural_width_px: null,
  natural_height_px: null,
  signing_identity_id: null,
  sign_mode: mode,
  sign_reason: "",
  signer: null,
});

const bootstrap = (mode: "server" | "local") => ({
  ...LOCAL_BOOTSTRAP,
  mode,
  auth: { ...LOCAL_BOOTSTRAP.auth, registration_mode: "open" as const },
  user: {
    id: AUTHOR.id,
    name: AUTHOR.name,
    email: "ivanov@edu.hse.ru",
    avatar_initials: "ИИ",
    is_instance_admin: false,
    email_verified: true,
    locale: null,
    org_roles: [],
  },
});

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const project = {
    id: PROJECT,
    authors: [],
    lang: "ru",
  } as unknown as Project;
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`${PATH}/route`]}>
          <Routes>
            <Route
              path={`${PATH}/route`}
              element={
                <SigningRouteEditor project={project} profileId={PROFILE} />
              }
            />
            <Route path={PATH} element={<p>checkpoint</p>} />
            <Route
              path={`/projects/${PROJECT}/submit/cp/pre-defense`}
              element={<p>other checkpoint</p>}
            />
            <Route path="/sign/:projectId/:routeId" element={<p>sign</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
};

const step = (n: number) => screen.findByTestId(`route-step-${String(n)}`);

beforeAll(() => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
});

const signatures = () => ({
  slots: {
    author: slotInfo("image"),
    supervisor: slotInfo("detached_text"),
    academic_supervisor: slotInfo("image"),
  },
  placements: {
    [DOC]: {
      author: placement(!unplaced.has("author")),
      supervisor: placement(!unplaced.has("supervisor")),
    },
  },
  frozen: {},
  detached: {},
  withheld: {},
  runtime_slots: [
    slotDef("author", "Студент"),
    slotDef("supervisor", "Научный руководитель"),
    slotDef("academic_supervisor", "Академический руководитель"),
  ],
});

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  demo.reset();
  cryptoDemo.reset();
  unplaced = new Set();
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("server"));
  vi.spyOn(documentApi, "list").mockResolvedValue([]);
  vi.spyOn(buildAvailabilityApi, "get").mockReturnValue(
    new Promise(() => undefined),
  );
  vi.spyOn(projectApi, "get").mockResolvedValue({ authors: [] } as never);
  vi.spyOn(projectInvitationsApi, "list").mockResolvedValue({
    items: [invitation("inv_co", "co_supervisor")],
    total: 1,
    limit: 50,
    offset: 0,
  });
  vi.spyOn(signatureApi, "getState").mockImplementation(() =>
    Promise.resolve(signatures()),
  );
  vi.spyOn(signatureApi, "updatePlacement").mockImplementation(
    (_project, _doc, slotId, data) => {
      if (data.enabled === true) unplaced.delete(slotId);
      return Promise.resolve(placement(!unplaced.has(slotId)));
    },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Отправка на подписание: черновик точки", () => {
  it("создаёт черновик из пака: шаги, документы, размещения и готовность", async () => {
    mount();
    expect(await step(1)).toHaveTextContent("Иванов И. И.");
    expect(await step(2)).toHaveTextContent("Петров П. П.");
    expect(within(await step(2)).getByText("ЭП")).toBeInTheDocument();
    expect(
      await screen.findByText("Всё готово к отправке."),
    ).toBeInTheDocument();
    expect(screen.getByTestId(`route-doc-${DOC}`)).toHaveTextContent("собран");
    // Редактор размещения видит только слоты маршрута; необязательный предлагается кнопкой.
    expect(await screen.findByTestId("stamp-editor")).toHaveTextContent(
      "author,supervisor",
    );
    expect(
      screen.getByTestId("route-add-slot-academic_supervisor"),
    ).toHaveTextContent("Добавить подпись: Академический руководитель");
    expect(screen.getByTestId("route-slot-supervisor")).toHaveTextContent(
      "стр. 1",
    );
    expect(screen.getByText("Картинка подписи загружена")).toBeInTheDocument();
  });

  it("подпись без места на странице мешает отправке; помеха ведёт к размещению", async () => {
    unplaced.add("supervisor");
    const user = userEvent.setup();
    mount();
    expect(await screen.findByTestId("route-blockers")).toHaveTextContent(
      "Научный руководитель (Заявление о выборе темы): подпись не размещена на странице",
    );
    expect(screen.getByTestId("route-send")).toBeDisabled();
    const row = await screen.findByTestId("route-slot-supervisor");
    expect(row).toHaveTextContent("не размещена");

    // «К размещению» ставит фокус на кнопку места этого слота в блоке «Где подписи».
    await user.click(screen.getByTestId("route-blocker-place-supervisor"));
    const place = within(row).getByRole("button", { name: "На стр. 1" });
    await waitFor(() => {
      expect(place).toHaveFocus();
    });

    await user.click(place);
    expect(signatureApi.updatePlacement).toHaveBeenCalledWith(
      PROJECT,
      DOC,
      "supervisor",
      expect.objectContaining({ enabled: true, page: 1 }),
    );
    expect(
      await screen.findByText("Всё готово к отправке."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("route-send")).toBeEnabled();
  });

  it("документ держит маршрут другой точки: помеха называет её, что сделать, и ведёт туда", async () => {
    const original = signingRouteApi.preview.bind(signingRouteApi);
    vi.spyOn(signingRouteApi, "preview").mockImplementation(
      async (...args) => ({
        ...(await original(...args)),
        can_send: false,
        blockers: [
          {
            code: "doc_in_other_route",
            doc_id: DOC,
            slot_id: null,
            participant_id: null,
            other_route: {
              id: "sr_other",
              profile: {
                id: "pre-defense",
                name: { ru: "Предзащита", en: "Pre-defence" },
              },
              status: "completed",
            },
          },
        ],
      }),
    );
    const user = userEvent.setup();
    mount();
    expect(await screen.findByTestId("route-blockers")).toHaveTextContent(
      "Заявление о выборе темы: документ держит завершённый маршрут контрольной точки «Предзащита». Чтобы отправить его здесь, нажмите «Снять с контроля» на странице той точки.",
    );
    expect(screen.getByTestId(`route-doc-${DOC}`)).toHaveTextContent(
      "держит завершённый маршрут «Предзащита»",
    );
    expect(screen.getByTestId("route-send")).toBeDisabled();
    await user.click(screen.getByTestId(`route-blocker-point-${DOC}`));
    expect(await screen.findByText("other checkpoint")).toBeInTheDocument();
  });

  it("идущий маршрут другой точки: отменить его там", async () => {
    const original = signingRouteApi.preview.bind(signingRouteApi);
    vi.spyOn(signingRouteApi, "preview").mockImplementation(
      async (...args) => ({
        ...(await original(...args)),
        can_send: false,
        blockers: [
          {
            code: "doc_in_other_route",
            doc_id: DOC,
            slot_id: null,
            participant_id: null,
            other_route: {
              id: "sr_other",
              profile: {
                id: "pre-defense",
                name: { ru: "Предзащита", en: "Pre-defence" },
              },
              status: "active",
            },
          },
        ],
      }),
    );
    mount();
    expect(await screen.findByTestId("route-blockers")).toHaveTextContent(
      "отмените тот маршрут на странице его точки",
    );
    expect(screen.getByTestId(`route-doc-${DOC}`)).toHaveTextContent(
      "на подписании в маршруте «Предзащита»",
    );
  });

  it("людей с персоной несколько: автор выбирает, кто подписывает", async () => {
    const user = userEvent.setup();
    mount();
    expect(await step(2)).toHaveTextContent("Петров П. П.");
    const pick = await screen.findByTestId("route-pick-supervisor");
    expect(pick).toHaveValue("member:u_demo_petrov");
    expect(
      within(pick)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Петров П. П.", "Сидорова А. В."]);
    // У автора кандидат один: выбирать не из кого.
    expect(screen.queryByTestId("route-pick-author")).toBeNull();

    await user.selectOptions(pick, "member:u_demo_sidorova");
    await waitFor(async () => {
      expect(await step(2)).toHaveTextContent("Сидорова А. В.");
    });
    const [summary] = (await signingRouteApi.list(PROJECT, PROFILE)).items;
    const saved = await signingRouteApi.get(PROJECT, summary?.id ?? "");
    expect(saved.steps[1]?.[0]?.user_id).toBe("u_demo_sidorova");
    expect(await screen.findByTestId("route-pick-supervisor")).toHaveValue(
      "member:u_demo_sidorova",
    );
  });

  it("необязательная подпись добавляет участника; приглашение снимает помеху", async () => {
    const create = vi.spyOn(projectInvitationsApi, "create").mockResolvedValue({
      invitation: invitation("inv_new", "academic_supervisor"),
      delivery: "inbox",
      link: null,
    });
    vi.spyOn(projectInvitationsApi, "draft").mockResolvedValue({ message: "" });
    const user = userEvent.setup();
    mount();
    await user.click(
      await screen.findByTestId("route-add-slot-academic_supervisor"),
    );

    const third = await step(3);
    expect(third).toHaveTextContent("Академический руководитель");
    expect(third).toHaveTextContent("нет в проекте");
    expect(await screen.findByTestId("route-blockers")).toHaveTextContent(
      "Академический руководитель: человека нет в проекте, пригласите",
    );
    expect(screen.getByTestId("route-send")).toBeDisabled();

    await user.click(within(third).getByTestId("route-invite"));
    await user.type(await screen.findByTestId("invite-email"), "kozlov@hse.ru");
    await user.click(screen.getByTestId("invite-submit"));
    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        PROJECT,
        expect.objectContaining({
          role: "reviewer",
          persona: "academic_supervisor",
        }),
      );
    });
    // Ссылка приглашения ведёт на страницу подписания этого маршрута.
    expect(create.mock.calls[0]?.[1].next).toMatch(/^\/sign\/p_demo\/sr_/);
    await waitFor(async () => {
      expect(await step(3)).toHaveTextContent("приглашение отправлено");
    });
    expect(
      await screen.findByText("Всё готово к отправке."),
    ).toBeInTheDocument();
  });

  it("согласующий подбирается по персоне из ожидающих приглашений", async () => {
    const user = userEvent.setup();
    mount();
    await step(2);
    await user.selectOptions(
      await screen.findByTestId("route-approver-persona"),
      "co_supervisor",
    );
    await user.click(screen.getByTestId("route-add-approver"));
    const third = await step(3);
    expect(third).toHaveTextContent("Соруководитель");
    expect(third).toHaveTextContent("только согласование");
    // Сервер (R5) ставит на персону ожидающее приглашение с ней, как в заготовке.
    await waitFor(async () => {
      expect(await step(3)).toHaveTextContent("c***@hse.ru");
    });
    expect(await step(3)).toHaveTextContent("приглашение отправлено");
  });
});

describe("Отправка на подписание: порядок", () => {
  const transfer = { setData: vi.fn(), dropEffect: "", effectAllowed: "" };

  it("научрука можно перетащить в шаг автора и обратно отдельным шагом", async () => {
    mount();
    const supervisor = await screen.findByTestId("route-person-supervisor");
    fireEvent.dragStart(supervisor, { dataTransfer: transfer });
    fireEvent.dragOver(await step(1), { dataTransfer: transfer });
    fireEvent.drop(await step(1), { dataTransfer: transfer });
    await waitFor(() => {
      expect(screen.queryByTestId("route-step-2")).not.toBeInTheDocument();
    });
    expect(await step(1)).toHaveTextContent("Петров П. П.");
    expect(await step(1)).toHaveTextContent("параллельно");

    fireEvent.dragStart(await screen.findByTestId("route-person-supervisor"), {
      dataTransfer: transfer,
    });
    fireEvent.drop(await screen.findByTestId("route-gap-0"), {
      dataTransfer: transfer,
    });
    await waitFor(async () => {
      expect(await step(1)).toHaveTextContent("Петров П. П.");
    });
    expect(await step(2)).toHaveTextContent("Иванов И. И.");
  });

  it("шаг двигается стрелками", async () => {
    const user = userEvent.setup();
    mount();
    await step(2);
    await user.click(screen.getByRole("button", { name: "Шаг 2 раньше" }));
    await waitFor(async () => {
      expect(await step(1)).toHaveTextContent("Петров П. П.");
    });
  });
});

describe("Отправка на подписание: отправка", () => {
  it("сохраняет сообщение, отправляет и возвращает на точку", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText("Всё готово к отправке.");
    await user.type(screen.getByTestId("route-message"), "Прошу подписать");
    await user.click(screen.getByTestId("route-send"));
    expect(await screen.findByText("checkpoint")).toBeInTheDocument();
    const [summary] = (await signingRouteApi.list(PROJECT, PROFILE)).items;
    expect(summary?.status).toBe("active");
    const route = await signingRouteApi.get(PROJECT, summary?.id ?? "");
    expect(route.message).toBe("Прошу подписать");
  });

  it("«Отправить и подписать»: подпись отказала после отправки, экран ведёт подписать", async () => {
    installDemoAdapter(apiClient, createDemoRouter(cryptoDemo.routes));
    try {
      const user = userEvent.setup();
      mount();
      const sign = await screen.findByTestId("route-send-sign");
      await user.type(screen.getByLabelText("Пароль ключа"), "broken");
      await user.click(sign);

      // Маршрут ушёл: это не сбой отправки, а неподписанный свой слот.
      const notice = await screen.findByTestId("route-my-turn");
      expect(notice).toHaveTextContent(
        "Маршрут отправлен, ваша подпись не поставлена. Подпишите на своей странице.",
      );
      expect(notice).toHaveTextContent(
        "Подписать ключом не удалось: The key refused to sign",
      );
      expect(screen.queryByTestId("route-send")).toBeNull();
      expect(screen.queryByText("checkpoint")).toBeNull();
      const [summary] = (await signingRouteApi.list(PROJECT, PROFILE)).items;
      expect(summary?.status).toBe("active");
      expect(within(notice).getByTestId("route-go-sign")).toHaveAttribute(
        "href",
        `/sign/${PROJECT}/${summary?.id ?? ""}`,
      );
    } finally {
      installDemoAdapter(apiClient, createDemoRouter(demo.routes));
    }
  });

  it("отказ до отправки остаётся ошибкой отправки", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText("Всё готово к отправке.");
    vi.spyOn(signingRouteApi, "send").mockRejectedValue(
      new ApiError("gpg отказал", "sign_failed", 400),
    );
    await user.click(screen.getByTestId("route-send"));
    expect(await screen.findByRole("alert")).toHaveTextContent("gpg отказал");
    expect(screen.queryByTestId("route-my-turn")).toBeNull();
    expect(screen.getByTestId("route-send")).toBeInTheDocument();
  });

  it("локальная Студия: маршрутов нет, экран так и говорит", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("local"));
    mount();
    expect(
      await screen.findByText(/работает на сервере Студии/),
    ).toBeInTheDocument();
    expect((await signingRouteApi.list(PROJECT, PROFILE)).items).toEqual([]);
  });
});
