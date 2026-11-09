import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
import { signingRouteApi } from "@entities/signing-route";
import {
  createSigningRouteDemo,
  type SigningDemoUser,
} from "@entities/signing-route/testing";
import { useDocSigningHold } from "../model/useDocSigningHold";
import { SigningHoldBanner } from "./SigningHoldBanner";

const PROJECT = "p_demo";
const PROFILE = "topic-approval";
const DOC = "topic_application";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };

const demo = createSigningRouteDemo({ getUser: () => AUTHOR });

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

/** Как в редакторе документа: плашка, если документ держит идущий маршрут. */
const Harness = ({ docId }: { docId: string }) => {
  const hold = useDocSigningHold(PROJECT, docId);
  return (
    <>
      <span data-testid="held">{hold === null ? "no" : "yes"}</span>
      {hold && <SigningHoldBanner projectId={PROJECT} hold={hold} />}
    </>
  );
};

const mount = (docId: string) =>
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
          <Harness docId={docId} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

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
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("server"));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("плашка документа на подписании", () => {
  it("документ идущего маршрута: шаг, запрет подписей и ход на точке", async () => {
    await startRoute();
    mount(DOC);
    const banner = await screen.findByTestId("signing-hold-banner");
    expect(banner).toHaveTextContent(
      "Документ на подписании (шаг 2 из 2). Правка и пересборка остановят маршрут.",
    );
    expect(banner).toHaveTextContent(
      "Подписи менять нельзя, пока маршрут идёт.",
    );
    expect(screen.getByTestId("signing-hold-open")).toHaveAttribute(
      "href",
      `/projects/${PROJECT}/submit/cp/${PROFILE}`,
    );
  });

  it("другой документ маршрут не держит", async () => {
    await startRoute();
    const get = vi.spyOn(signingRouteApi, "get");
    mount("vkr");
    await waitFor(() => {
      expect(get).toHaveBeenCalled();
    });
    expect(screen.getByTestId("held")).toHaveTextContent("no");
  });

  it("остановленный маршрут подписи не держит", async () => {
    await startRoute();
    demo.rebuild(PROJECT, DOC);
    const list = vi.spyOn(signingRouteApi, "list");
    const get = vi.spyOn(signingRouteApi, "get");
    mount(DOC);
    await waitFor(() => {
      expect(list).toHaveBeenCalled();
    });
    expect(get).not.toHaveBeenCalled();
    expect(screen.queryByTestId("signing-hold-banner")).toBeNull();
  });

  it("локальная Студия маршрутов не спрашивает", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(bootstrap("local"));
    const list = vi.spyOn(signingRouteApi, "list");
    mount(DOC);
    await waitFor(() => {
      expect(sessionApi.bootstrap).toHaveBeenCalled();
    });
    expect(list).not.toHaveBeenCalled();
    expect(screen.getByTestId("held")).toHaveTextContent("no");
  });

  it("по-английски", async () => {
    await i18n.changeLanguage("en");
    await startRoute();
    mount(DOC);
    expect(await screen.findByTestId("signing-hold-banner")).toHaveTextContent(
      "This document is out for signing (step 2 of 2).",
    );
  });
});
