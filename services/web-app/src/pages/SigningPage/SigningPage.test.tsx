import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { I18nextProvider } from "react-i18next";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@shared/api";
import { createDemoRouter, installDemoAdapter } from "@shared/api/demo";
import { i18n } from "@shared/lib";
import { loadSigningNamespace } from "@shared/lib/i18n/signingNamespace";
import { signingRouteApi, signingTaskApi } from "@entities/signing-route";
import {
  DEMO_SIGNING_MEMBERS,
  createSigningRouteDemo,
  type SigningDemoUser,
} from "@entities/signing-route/testing";

// Страница целиком на настоящих хуках сущности поверх моков контракта (как будет с R6).

vi.mock("@widgets/AppTitlebar", () => ({ AppTitlebar: () => null }));
vi.mock("@widgets/AppStatusBar", () => ({ AppStatusBar: () => null }));
vi.mock("@shared/ui", async () => ({
  ...(await vi.importActual<Record<string, unknown>>("@shared/ui")),
  PdfViewer: ({ url }: { url: string }) => (
    <div data-testid="pdf-viewer" data-url={url} />
  ),
}));

import { SigningPage } from "./SigningPage";

const PROJECT = "p_01hxa1c4de";
const PROFILE = "topic-approval";
const AUTHOR: SigningDemoUser = { id: "u_author", name: "Иванов И. И." };
const SUPERVISOR: SigningDemoUser = {
  id: "u_demo_petrov",
  name: "Петров П. П.",
};
const ACADEMIC: SigningDemoUser = { id: "u_sidorov", name: "Сидоров С. С." };
const STRANGER: SigningDemoUser = { id: "u_stranger", name: "Чужой Ч." };

let me: SigningDemoUser = AUTHOR;
const demo = createSigningRouteDemo({
  getUser: () => me,
  members: [
    ...DEMO_SIGNING_MEMBERS,
    {
      user_id: ACADEMIC.id,
      name: ACADEMIC.name,
      persona: "academic_supervisor",
    },
  ],
});

/** Автор отправил «Заявку на тему КП»: он, затем научрук ЭП, затем академрук картинкой. */
const sendRoute = async (): Promise<string> => {
  me = AUTHOR;
  const route = await signingRouteApi.create(PROJECT, PROFILE);
  await signingRouteApi.update(PROJECT, route.id, {
    steps: [
      ...route.steps.map((step) =>
        step.map((p) => ({
          id: p.id,
          persona: p.persona,
          user_id: p.user_id,
          invitation_id: p.invitation_id,
        })),
      ),
      [
        {
          id: null,
          persona: "academic_supervisor",
          user_id: ACADEMIC.id,
          invitation_id: null,
        },
      ],
    ],
    extra_slots: [
      { doc_id: "topic_application", slot_id: "academic_supervisor" },
    ],
    deadline: "2026-11-15T20:59:00Z",
    message: "Прошу подписать до пятницы.",
  });
  const preview = await signingRouteApi.preview(PROJECT, route.id);
  await signingRouteApi.send(PROJECT, route.id, {
    expected: Object.fromEntries(
      preview.docs.map((d) => [d.doc_id, d.token ?? ""]),
    ),
    sign: null,
  });
  return route.id;
};

const open = (routeId: string, as: SigningDemoUser) => {
  me = as;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/sign/${PROJECT}/${routeId}`]}>
          <Routes>
            <Route path="/sign/:projectId/:routeId" element={<SigningPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
};

const pageState = () =>
  screen.getByTestId("signing-page").getAttribute("data-state");

beforeAll(async () => {
  installDemoAdapter(apiClient, createDemoRouter(demo.routes));
  await loadSigningNamespace();
});

beforeEach(async () => {
  demo.reset();
  me = AUTHOR;
  await i18n.changeLanguage("ru");
});

describe("страница подписанта на моках контракта", () => {
  it("научрук согласует в свою очередь и ждёт итоговый PDF", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute();
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(pageState()).toBe("turn");
    });
    expect(screen.getByTestId("signing-head")).toHaveTextContent(
      "Иванов И. И. просит подписать",
    );
    expect(screen.getByTestId("pdf-viewer").getAttribute("data-url")).toMatch(
      /\/api\/v1\/projects\/p_01hxa1c4de\/docs\/topic_application\/pdf\/signed$/,
    );
    await user.click(screen.getByTestId("signing-approve"));
    await waitFor(() => {
      expect(pageState()).toBe("approved");
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "вас попросят подписать итоговый PDF",
    );
  });

  it("академрук ждёт очереди, затем согласует картинкой и видит, кто дальше", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute();
    const view = open(routeId, ACADEMIC);
    await waitFor(() => {
      expect(pageState()).toBe("not_yet");
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Сейчас: Петров П. П.",
    );
    view.unmount();

    me = SUPERVISOR;
    const task = await signingTaskApi.get(PROJECT, routeId);
    await signingTaskApi.approve(PROJECT, routeId, {
      expected: { topic_application: task.docs[0]?.token ?? "" },
      method: null,
      sign: null,
    });

    const second = open(routeId, ACADEMIC);
    await waitFor(() => {
      expect(pageState()).toBe("turn");
    });
    // Картинки ещё нет: «Согласовать» ждёт её (загрузка картинки появится в W5).
    expect(screen.getByTestId("signing-approve")).toBeDisabled();
    second.unmount();

    await signingTaskApi.uploadImage(
      PROJECT,
      routeId,
      new Blob(["png"], { type: "image/png" }),
      false,
    );
    open(routeId, ACADEMIC);
    await waitFor(() => {
      expect(screen.getByTestId("signing-approve")).toBeEnabled();
    });
    await user.click(screen.getByTestId("signing-approve"));
    await waitFor(() => {
      expect(pageState()).toBe("done");
    });
    // Документы зафиксированы, научрук подписывает итоговый PDF.
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Следующим подписывает Петров П. П.",
    );
  });

  it("возврат на доработку с комментарием", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute();
    open(routeId, SUPERVISOR);
    await user.click(await screen.findByTestId("signing-return"));
    await user.type(
      await screen.findByTestId("signing-return-comment"),
      "Уточните цель проекта",
    );
    await user.click(screen.getByTestId("signing-return-submit"));
    await waitFor(() => {
      expect(pageState()).toBe("returned");
    });
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "Вы вернули документы на доработку",
    );
    expect(screen.getByTestId("signing-status")).toHaveTextContent(
      "«Уточните цель проекта»",
    );
    expect(screen.queryByTestId("signing-return")).not.toBeInTheDocument();
  });

  it("маршрут отменили, пока страница была открыта: отказ и новое состояние", async () => {
    const user = userEvent.setup();
    const routeId = await sendRoute();
    open(routeId, SUPERVISOR);
    await waitFor(() => {
      expect(pageState()).toBe("turn");
    });
    me = AUTHOR;
    await signingRouteApi.cancel(PROJECT, routeId);
    me = SUPERVISOR;
    await user.click(screen.getByTestId("signing-approve"));
    await waitFor(() => {
      expect(pageState()).toBe("cancelled");
    });
    expect(screen.getByTestId("signing-failure")).toHaveAttribute(
      "data-code",
      "not_your_turn",
    );
  });

  it("не участнику страница не найдена", async () => {
    const routeId = await sendRoute();
    open(routeId, STRANGER);
    await waitFor(() => {
      expect(pageState()).toBe("not_found");
    });
  });
});
