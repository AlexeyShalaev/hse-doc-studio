import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { InboxPanel } from "@features/inbox";
import { inboxApi } from "@entities/invitation";
import { signingRouteApi } from "@entities/signing-route";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";

// «На подпись» поверх демо-транспорта (срез W6): автор отправляет маршрут, научрук видит задачу
// во «Входящих» и счётчике колокольчика.

const OWN = "p_01hxa1c4de";
const PROFILE = "topic-approval";

const Where = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
};

const mountInbox = (path: string) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/inbox" element={<InboxPanel />} />
            <Route path="*" element={null} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

/** Автор (студент сценария) отправляет черновик точки; возвращает id маршрута. */
const sendAsAuthor = async (): Promise<string> => {
  const route = await signingRouteApi.create(OWN, PROFILE);
  const preview = await signingRouteApi.preview(OWN, route.id);
  const expected = Object.fromEntries(
    preview.docs.map((d) => [d.doc_id, d.token ?? ""]),
  );
  await signingRouteApi.send(OWN, route.id, { expected, sign: null });
  return route.id;
};

const signInAsSupervisor = () => {
  const world = getServerWorld();
  const user = world.bootstrap.user;
  if (user === null) throw new Error("demo user not signed in");
  world.bootstrap = {
    ...world.bootstrap,
    user: { ...user, id: "u_demo_petrov", name: "Петров П. П." },
  };
};

beforeAll(() => {
  installServerDemo();
  enableServerDemo();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  activateServerScenario("student_ready");
});
afterEach(cleanup);

describe("демо «Входящие»: на подпись", () => {
  it("сводка считает задачи подписанта, у автора их нет", async () => {
    expect((await inboxApi.summary()).signing_tasks).toBe(0);
    await sendAsAuthor();
    expect((await inboxApi.summary()).signing_tasks).toBe(0);
    signInAsSupervisor();
    expect((await inboxApi.summary()).signing_tasks).toBe(1);
  });

  it("вкладка из адреса показывает задачу, «Открыть» ведёт на страницу подписи", async () => {
    const user = userEvent.setup();
    const routeId = await sendAsAuthor();
    signInAsSupervisor();
    mountInbox("/inbox?tab=signing");
    expect(screen.getByTestId("inbox-tab-signing")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const card = await screen.findByTestId(`inbox-signing-task-${routeId}`);
    expect(card).toHaveTextContent("Заявка на тему КП");
    expect(within(card).getByTestId("inbox-signing-action")).toHaveTextContent(
      "Согласовать и подписать",
    );
    await user.click(within(card).getByTestId(`inbox-signing-open-${routeId}`));
    expect(screen.getByTestId("where")).toHaveTextContent(
      `/sign/${OWN}/${routeId}`,
    );
  });

  it("переключение вкладок пишет её в адрес", async () => {
    const user = userEvent.setup();
    mountInbox("/inbox");
    await user.click(screen.getByTestId("inbox-tab-signing"));
    expect(screen.getByTestId("where")).toHaveTextContent("/inbox?tab=signing");
    expect(
      await screen.findByTestId("inbox-signing-empty"),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("inbox-tab-all"));
    expect(screen.getByTestId("where").textContent).toBe("/inbox");
  });
});
