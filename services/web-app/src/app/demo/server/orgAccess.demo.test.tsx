import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n, useToastStore } from "@shared/lib";
import { ApiError, apiClient } from "@shared/api";
import { MyOrganizationsSection } from "@features/my-organizations";
import { ProjectAccessPanel } from "@features/project-access";
import { projectAccessApi } from "../../../features/project-access/api/projectAccessApi";
import type { ProjectRole } from "@entities/session";
import { installServerDemo } from "../index";
import { activateServerScenario, enableServerDemo } from "./index";
import { getServerWorld } from "./routes";

// Организации участника и панель «Доступ» поверх демо-транспорта: те же запросы,
// что уйдут настоящему бэкенду, и ответы, проходящие те же схемы.

const mountWith = (ui: React.ReactNode) =>
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
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const toastTexts = () =>
  useToastStore
    .getState()
    .toasts.map((t) => `${t.title ?? ""} ${t.message ?? ""}`);

const OWN = "p_01hxa1c4de";
const FOREIGN_ORG = "p_01hxa2f8gh";

beforeAll(() => {
  installServerDemo();
  enableServerDemo();
});
beforeEach(async () => {
  await i18n.changeLanguage("ru");
  useToastStore.getState().clear();
});
afterEach(cleanup);

describe("демо: раздел «Организации»", () => {
  it("студент видит организацию, роль и группу, выходит с подтверждением", async () => {
    activateServerScenario("student_ready");
    const user = userEvent.setup();
    mountWith(<MyOrganizationsSection />);
    const card = await screen.findByTestId("my-org-msp-2025");
    expect(within(card).getByTestId("my-org-role-msp-2025")).toHaveTextContent(
      "Участник",
    );
    expect(within(card).getByText("Команда Bertie")).toBeInTheDocument();
    // Рядовой участник не видит ссылку в админку организации.
    expect(screen.queryByTestId("my-org-manage-msp-2025")).toBeNull();

    await user.click(screen.getByTestId("my-org-leave-msp-2025"));
    await user.click(await screen.findByTestId("my-org-leave-confirm"));
    expect(await screen.findByTestId("my-orgs-empty")).toBeInTheDocument();
    expect(toastTexts().join("\n")).toContain("Вы вышли из организации");
    expect(getServerWorld().bootstrap.user?.org_roles).toEqual([]);
  });

  it("единственный владелец не выходит: кнопка закрыта, сервер отвечает last_owner", async () => {
    activateServerScenario("admin_ready");
    mountWith(<MyOrganizationsSection />);
    const leave = await screen.findByTestId("my-org-leave-msp-2025");
    expect(leave).toBeDisabled();
    expect(
      screen.getAllByText(/единственный владелец/i).length,
    ).toBeGreaterThan(0);
    // Ссылка в админку организации есть у владельца.
    expect(screen.getByTestId("my-org-manage-msp-2025")).toHaveAttribute(
      "href",
      "/admin/orgs/msp-2025",
    );
    const error = await apiClient
      .delete("/account/orgs/msp-2025/membership", { silentError: true })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("last_owner");
  });

  it("без организаций: пустое состояние", async () => {
    activateServerScenario("admin_no_orgs");
    mountWith(<MyOrganizationsSection />);
    expect(await screen.findByTestId("my-orgs-empty")).toHaveTextContent(
      "Вы не состоите ни в одной организации",
    );
  });
});

describe("демо: панель «Доступ»", () => {
  const mount = (projectId: string, role: ProjectRole) =>
    mountWith(<ProjectAccessPanel projectId={projectId} myRole={role} />);

  it("владелец видит людей и группы, добавляет группу, роль названа в тосте", async () => {
    activateServerScenario("student_ready");
    const user = userEvent.setup();
    mount(OWN, "owner");
    const list = await screen.findByTestId("access-list");
    expect(
      within(list).getByTestId("access-fixed-user:u_01hx7k2m9c"),
    ).toHaveTextContent("Владелец");
    expect(
      within(list).getByTestId("access-row-group:g_01hx7m4c2d"),
    ).toHaveTextContent("Команда Bertie");

    await user.type(screen.getByTestId("access-search"), "Наставн");
    await user.click(
      await screen.findByTestId("access-add-group:g_01hx7m5d3e"),
    );
    expect(
      await screen.findByTestId("access-row-group:g_01hx7m5d3e"),
    ).toBeInTheDocument();
    expect(toastTexts().join("\n")).toContain("«Читатель»");
  });

  it("поиск без результата объясняет, почему", async () => {
    activateServerScenario("student_ready");
    const user = userEvent.setup();
    mount(OWN, "owner");
    await screen.findByTestId("access-list");
    await user.type(screen.getByTestId("access-search"), "zzzz");
    expect(await screen.findByTestId("access-none")).toBeInTheDocument();
  });

  it("не владелец видит список без управления", async () => {
    activateServerScenario("student_ready");
    mount(FOREIGN_ORG, "reviewer");
    expect(await screen.findByTestId("access-list")).toBeInTheDocument();
    expect(screen.queryByTestId("access-add")).toBeNull();
    expect(
      screen.getByText(/Менять доступ может владелец/),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("access-fixed-org:org_01hx5a"),
    ).toBeInTheDocument();
  });

  it("отказ по роли называет нужную роль в тосте", async () => {
    activateServerScenario("student_ready");
    await expect(
      projectAccessApi.set(FOREIGN_ORG, {
        subject_kind: "user",
        subject_id: "u_01hx7k4p6g",
        role: "reader",
      }),
    ).rejects.toBeInstanceOf(ApiError);
    await waitFor(() => {
      expect(toastTexts().join("\n")).toContain("нужна роль «Владелец»");
    });
  });

  it("роль владельца проекта не меняется и не выдаётся через панель", async () => {
    activateServerScenario("student_ready");
    const owner = await projectAccessApi
      .set(OWN, {
        subject_kind: "user",
        subject_id: "u_01hx7k2m9c",
        role: "reader",
      })
      .catch((e: unknown) => e);
    expect((owner as ApiError).code).toBe("last_owner");
    const grant = await projectAccessApi
      .set(OWN, {
        subject_kind: "user",
        subject_id: "u_01hx7k4p6g",
        role: "owner",
      })
      .catch((e: unknown) => e);
    expect((grant as ApiError).code).toBe("input_invalid");
  });

  it("удаление из группы закрывает доступ: у проекта остаётся роль только по прямой записи", async () => {
    activateServerScenario("student_ready");
    await projectAccessApi.set(OWN, {
      subject_kind: "user",
      subject_id: "u_01hx7k4p6g",
      role: "reviewer",
    });
    await projectAccessApi.remove(OWN, "user", "u_01hx7k4p6g");
    const { items: entries } = await projectAccessApi.list(
      OWN,
      { limit: 50, offset: 0 },
      new AbortController().signal,
    );
    expect(entries.some((e) => e.subject_id === "u_01hx7k4p6g")).toBe(false);
  });
});
