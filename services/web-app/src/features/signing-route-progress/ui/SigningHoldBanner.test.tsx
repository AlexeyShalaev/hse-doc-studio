import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
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
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import {
  expectedTokens,
  signingRouteApi,
  signingTaskApi,
} from "@entities/signing-route";
import {
  createSigningRouteDemo,
  type SigningDemoUser,
} from "@entities/signing-route/testing";
import { formatDay } from "../lib/format";
import {
  useDocRouteVersion,
  useDocSigningHold,
} from "../model/useDocSigningHold";
import { SigningHoldBanner } from "./SigningHoldBanner";

const PROJECT = "p_demo";
const PROFILE = "topic-approval";
const DOC = "topic_application";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const PETROV: SigningDemoUser = { id: "u_demo_petrov", name: "Петров П. П." };

let user: SigningDemoUser = AUTHOR;
const demo = createSigningRouteDemo({ getUser: () => user });

const bootstrap = (mode: "server" | "local") => ({
  ...LOCAL_BOOTSTRAP,
  mode,
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

/**
 * Как в редакторе документа: плашка, если документ держит идущий маршрут или у него есть
 * изменения после отправки на подпись.
 */
const Harness = ({
  docId,
  canManage,
}: {
  docId: string;
  canManage: boolean;
}) => {
  const hold = useDocSigningHold(PROJECT, docId);
  const version = useDocRouteVersion(PROJECT, docId);
  return (
    <>
      <span data-testid="held">{hold === null ? "no" : "yes"}</span>
      <SigningHoldBanner
        projectId={PROJECT}
        docId={docId}
        hold={hold}
        version={version}
        canManage={canManage}
      />
    </>
  );
};

const mount = (docId: string, { canManage = true } = {}) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <MemoryRouter>
          <Harness docId={docId} canManage={canManage} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

// Сессия и план подписей документа идут друг за другом: под нагрузкой это дольше секунды.
const LOAD = { timeout: 5000 };

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

describe("плашка документа на подписании", () => {
  it("документ идущего маршрута: шаг, версия на подписи, запрет подписей и ход на точке", async () => {
    await startRoute();
    mount(DOC);
    const banner = await screen.findByTestId("signing-hold-banner", {}, LOAD);
    expect(banner).toHaveTextContent(
      `Документ на подписании (шаг 2 из 2). Подписывают версию от ${formatDay(new Date().toISOString())}, ваши правки в неё не попадут.`,
    );
    expect(banner).toHaveAttribute("data-changed", "false");
    expect(screen.queryByTestId("signing-new-version")).toBeNull();
    expect(screen.queryByTestId("signing-hold-version")).toBeNull();
    expect(banner).toHaveTextContent(
      "Подписи менять нельзя, пока маршрут идёт.",
    );
    expect(screen.getByTestId("signing-hold-open")).toHaveAttribute(
      "href",
      `/projects/${PROJECT}/submit/cp/${PROFILE}`,
    );
  });

  it("маршрут документа приходит с его планом подписей: одним запросом", async () => {
    await startRoute();
    const plan = vi.spyOn(signatureApi, "getPlan");
    const list = vi.spyOn(signingRouteApi, "list");
    const get = vi.spyOn(signingRouteApi, "get");
    mount(DOC);
    await screen.findByTestId("signing-hold-banner", {}, LOAD);
    expect(plan).toHaveBeenCalledTimes(1);
    expect(plan.mock.calls[0]?.slice(0, 2)).toEqual([PROJECT, { docId: DOC }]);
    expect(list).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });

  it("другой документ маршрут не держит", async () => {
    await startRoute();
    const plan = vi.spyOn(signatureApi, "getPlan");
    mount("vkr");
    await waitFor(() => {
      expect(plan.mock.results[0]?.type).toBe("return");
    });
    await plan.mock.results[0]?.value;
    expect(screen.getByTestId("held")).toHaveTextContent("no");
  });

  it("версии на подписи у документа нет: текст без даты", async () => {
    await startRoute();
    const real = signatureApi.getPlan.bind(signatureApi);
    vi.spyOn(signatureApi, "getPlan").mockImplementation(async (...args) => {
      const plan = await real(...args);
      return {
        ...plan,
        docs: plan.docs.map((doc) => ({
          ...doc,
          pinned: null,
          working_differs: false,
        })),
      };
    });
    mount(DOC);
    expect(
      await screen.findByTestId("signing-hold-banner", {}, LOAD),
    ).toHaveTextContent(
      "Документ на подписании (шаг 2 из 2). Правка и пересборка остановят маршрут.",
    );
  });

  it("пересобран после отправки: маршрут идёт, плашка про изменения и новая версия", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    const u = userEvent.setup();
    mount(DOC);
    const changed = await screen.findByTestId("signing-hold-changed", {}, LOAD);
    const day = formatDay(new Date().toISOString());
    expect(changed).toHaveTextContent(
      `Есть изменения после отправки на подпись. Подписывают версию от ${day}.`,
    );
    expect(screen.getByTestId("held")).toHaveTextContent("yes");
    const banner = screen.getByTestId("signing-hold-banner");
    expect(banner).toHaveAttribute("data-changed", "true");
    // Дату версии называет строка про изменения, шаг идёт без неё.
    expect(banner).toHaveTextContent("Документ на подписании (шаг 2 из 2).");
    expect(banner).not.toHaveTextContent("ваши правки в неё не попадут");
    expect(screen.getByTestId("signing-hold-version")).toHaveAttribute(
      "href",
      expect.stringMatching(
        new RegExp(`/api/v1/projects/${PROJECT}/docs/${DOC}/pdf/signed$`),
      ),
    );

    await u.click(screen.getByTestId("signing-new-version"));
    const dialog = await screen.findByRole("dialog", {}, LOAD);
    expect(
      within(dialog).getByTestId("signing-new-version-changed"),
    ).toHaveTextContent("Изменились: Заявление о выборе темы.");
    await u.click(within(dialog).getByTestId("signing-new-version-confirm"));
    await waitFor(() => {
      expect(screen.queryByTestId("signing-hold-changed")).toBeNull();
    }, LOAD);
    expect(screen.getByTestId("signing-hold-banner")).toHaveAttribute(
      "data-changed",
      "false",
    );
  });

  it("читателю изменения видны, а «Отправить новую версию» нет", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    mount(DOC, { canManage: false });
    await screen.findByTestId("signing-hold-changed", {}, LOAD);
    expect(screen.queryByTestId("signing-new-version")).toBeNull();
    expect(screen.getByTestId("signing-hold-version")).toBeInTheDocument();
  });

  it("все подписали, потом правка: подписи свободны, плашка про изменения после подписания", async () => {
    const id = await startRoute();
    user = PETROV;
    const task = await signingTaskApi.get(PROJECT, id);
    await signingTaskApi.approve(PROJECT, id, {
      expected: expectedTokens(task),
      method: null,
      sign: { identity_id: null, passphrase: null },
    });
    user = AUTHOR;
    expect((await signingRouteApi.get(PROJECT, id)).status).toBe("completed");
    demo.rebuild(PROJECT, DOC);
    mount(DOC);
    const changed = await screen.findByTestId("signing-hold-changed", {}, LOAD);
    expect(changed).toHaveTextContent(
      `Все подписали версию от ${formatDay(new Date().toISOString())}. Есть изменения после подписания.`,
    );
    expect(screen.getByTestId("held")).toHaveTextContent("no");
    expect(screen.getByTestId("signing-new-version")).toBeInTheDocument();
  });

  it("перенос 0.20.0 не нашёл версию: восстановить нельзя, только новая версия", async () => {
    demo.seed({
      projectId: PROJECT,
      profileId: PROFILE,
      sender: AUTHOR,
      signer: PETROV,
      persona: "supervisor",
      state: "migration_lost",
    });
    mount(DOC);
    const changed = await screen.findByTestId("signing-hold-changed", {}, LOAD);
    expect(changed).toHaveTextContent(
      "Версию, отправленную на подпись, восстановить нельзя: отправьте новую версию.",
    );
    expect(screen.getByTestId("held")).toHaveTextContent("no");
    expect(screen.getByTestId("signing-new-version")).toBeInTheDocument();
    expect(screen.queryByTestId("signing-hold-version")).toBeNull();
  });

  it("остановленный маршрут подписи не держит", async () => {
    await startRoute();
    demo.tamper(PROJECT, DOC);
    const plan = vi.spyOn(signatureApi, "getPlan");
    mount(DOC);
    await waitFor(() => {
      expect(plan.mock.results[0]?.type).toBe("return");
    });
    const loaded = (await plan.mock.results[0]?.value) as {
      route: { status: string; stop_reason: string | null } | null;
    };
    expect(loaded.route).toMatchObject({
      status: "paused",
      stop_reason: "sent_changed",
    });
    // Подписи свободны; версию подменили, поэтому рабочая сборка от неё отличается.
    expect(screen.getByTestId("held")).toHaveTextContent("no");
    expect(
      await screen.findByTestId("signing-hold-banner", {}, LOAD),
    ).toHaveAttribute("data-changed", "true");
  });

  it("локальная Студия маршрутов не спрашивает", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("local"));
    const plan = vi.spyOn(signatureApi, "getPlan");
    mount(DOC);
    await waitFor(() => {
      expect(sessionApi.bootstrap).toHaveBeenCalled();
    });
    expect(plan).not.toHaveBeenCalled();
    expect(screen.getByTestId("held")).toHaveTextContent("no");
  });

  it("гость по ссылке маршрутов не спрашивает", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
      ...bootstrap("server"),
      user: null,
    });
    const plan = vi.spyOn(signatureApi, "getPlan");
    mount(DOC);
    await waitFor(() => {
      expect(sessionApi.bootstrap).toHaveBeenCalled();
    });
    expect(plan).not.toHaveBeenCalled();
    expect(screen.getByTestId("held")).toHaveTextContent("no");
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    await startRoute();
    mount(DOC);
    expect(
      await screen.findByTestId("signing-hold-banner", {}, LOAD),
    ).toHaveTextContent("This document is out for signing (step 2 of 2).");
  });
});
