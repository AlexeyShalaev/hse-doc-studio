import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n, toast } from "@shared/lib";
import { inboxApi, type MyInvitation } from "@entities/invitation";
import {
  accountSigningApi,
  type SigningTaskSummary,
} from "@entities/signing-route";
import { InboxPanel } from "./InboxPanel";

// «Принять» во «Входящих» (docs/design/signing-route.md, 6.5): приглашение подписанта маршрута,
// чья очередь уже настала, ведёт на страницу подписи, как ссылка приглашения с `?next=`.

const PROJECT = "p_signer";

const invitation: MyInvitation = {
  id: "inv_1",
  project: { id: PROJECT, name: "Bertie", owner_name: "Иванов И. И." },
  role: "reviewer",
  persona: "supervisor",
  message: null,
  invited_by: { id: "u_author", name: "Иванов И. И." },
  created_at: "2026-11-10T09:00:00Z",
  expires_at: "2099-11-17T09:00:00Z",
  status: "pending",
};

const task = (over: Partial<SigningTaskSummary> = {}): SigningTaskSummary => ({
  project: { id: PROJECT, name: "Bertie" },
  route_id: "sr_1",
  profile: {
    id: "topic-approval",
    name: { ru: "Заявка на тему КП", en: "Course project topic application" },
  },
  round: 1,
  sender: "Иванов И. И.",
  deadline: null,
  next_action: "approve",
  since: "2026-11-10T09:00:00Z",
  ...over,
});

const Where = () => {
  const { pathname } = useLocation();
  return <output data-testid="where">{pathname}</output>;
};

const mount = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <MemoryRouter initialEntries={["/inbox"]}>
          <Routes>
            <Route path="/inbox" element={<InboxPanel />} />
            <Route path="*" element={null} />
          </Routes>
          <Where />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

/** Задачи «На подпись» до и после принятия: принятие ставит человека в маршрут. */
const serve = (afterAccept: SigningTaskSummary[]) => {
  let accepted = false;
  vi.spyOn(inboxApi, "invitations").mockImplementation(() =>
    Promise.resolve(accepted ? [] : [invitation]),
  );
  vi.spyOn(inboxApi, "transfers").mockResolvedValue([]);
  vi.spyOn(inboxApi, "myRequests").mockResolvedValue([]);
  vi.spyOn(inboxApi, "notifications").mockResolvedValue({
    items: [],
    total: 0,
    limit: 100,
    offset: 0,
  });
  vi.spyOn(inboxApi, "summary").mockResolvedValue({
    unread: 0,
    invitations: 0,
    transfers: 0,
    access_requests: 0,
    signing_tasks: 0,
  });
  vi.spyOn(inboxApi, "accept").mockImplementation(() => {
    accepted = true;
    return Promise.resolve({ ...invitation, status: "accepted" });
  });
  return vi
    .spyOn(accountSigningApi, "tasks")
    .mockImplementation(() =>
      Promise.resolve({ items: accepted ? afterAccept : [] }),
    );
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("«Входящие»: принять приглашение", () => {
  it("подписант маршрута, чья очередь настала, попадает на страницу подписи", async () => {
    serve([
      task({ project: { id: "p_other", name: "Чужой" }, route_id: "sr_x" }),
      task(),
    ]);
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount();
    await u.click(
      await screen.findByTestId(`inbox-invitation-accept-${invitation.id}`),
    );
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/sign/${PROJECT}/sr_1`,
      );
    });
    expect(success).toHaveBeenCalledWith(
      "Вы в проекте «Bertie»: открываем страницу подписи",
    );
  });

  it("очередь ещё не дошла: в проект, как раньше", async () => {
    serve([task({ project: { id: "p_other", name: "Чужой" } })]);
    const success = vi.spyOn(toast, "success");
    const u = userEvent.setup();
    mount();
    await u.click(
      await screen.findByTestId(`inbox-invitation-accept-${invitation.id}`),
    );
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/projects/${PROJECT}`,
      );
    });
    expect(success).toHaveBeenCalledWith("Вы в проекте «Bertie»");
  });

  it("задачи не прочитались: принятие состоялось, ведём в проект", async () => {
    const tasks = serve([]);
    const u = userEvent.setup();
    mount();
    await screen.findByTestId(`inbox-invitation-accept-${invitation.id}`);
    tasks.mockRejectedValue(new Error("offline"));
    await u.click(
      screen.getByTestId(`inbox-invitation-accept-${invitation.id}`),
    );
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent(
        `/projects/${PROJECT}`,
      );
    });
  });
});
