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
import { apiClient } from "@shared/api";
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

const demo = createSigningRouteDemo({
  getUser: () => AUTHOR,
  invitations: [
    { invitation_id: "inv_co", persona: "co_supervisor", hint: "c***@hse.ru" },
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

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  demo.reset();
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
  vi.spyOn(signatureApi, "getState").mockResolvedValue({
    slots: {
      author: slotInfo("image"),
      supervisor: slotInfo("detached_text"),
      academic_supervisor: slotInfo("image"),
    },
    placements: {
      [DOC]: { author: placement(true), supervisor: placement(false) },
    },
    frozen: {},
    detached: {},
    runtime_slots: [
      slotDef("author", "Студент"),
      slotDef("supervisor", "Научный руководитель"),
      slotDef("academic_supervisor", "Академический руководитель"),
    ],
  });
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
      "не размещена",
    );
    expect(screen.getByText("Картинка подписи загружена")).toBeInTheDocument();
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
    await waitFor(async () => {
      expect(await step(3)).toHaveTextContent("приглашение отправлено");
    });
    expect(
      await screen.findByText("Всё готово к отправке."),
    ).toBeInTheDocument();
  });

  it("согласующий из ожидающих приглашений", async () => {
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
    await user.selectOptions(
      within(third).getByRole("combobox", { name: "Из приглашений" }),
      "inv_co",
    );
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

  it("локальная Студия: маршрутов нет, экран так и говорит", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("local"));
    mount();
    expect(
      await screen.findByText(/работает на сервере Студии/),
    ).toBeInTheDocument();
    expect((await signingRouteApi.list(PROJECT, PROFILE)).items).toEqual([]);
  });
});
