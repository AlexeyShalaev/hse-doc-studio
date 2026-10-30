import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import {
  AdminGroupSchema,
  AdminOrgMemberSchema,
  AdminOrgSchema,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import { serverAdminDemoRoutes } from "@/app/demo/server/routes";
import { ensureAdminOrgsLocales } from "./lib/locales";
import { assignableRoles, canEditMember, isLastOwner } from "./lib/permissions";
import { isValidSlug, slugify } from "./lib/slug";
import { OrgDetail, OrgsList } from "./index";

// Организации поверх демо-транспорта: те же запросы, что уйдут настоящему бэкенду,
// и ответы, проходящие те же схемы.

const client = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const wrap = (node: React.ReactNode) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={client()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

const router = createDemoRouter(serverAdminDemoRoutes);
const call = async (
  method: DemoRequest["method"],
  path: string,
  body?: unknown,
  query: Record<string, string> = {},
) => {
  const found = router.match(method, path);
  if (!found) throw new Error(`no demo route ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query,
    body,
    forward: () => Promise.reject(new Error("forward")),
  });
};
const codeOf = (res: { data?: unknown }) =>
  (res.data as { code?: string }).code;

const Detail = ({
  slug,
  onDeleted = () => undefined,
}: {
  slug: string;
  onDeleted?: () => void;
}) => <OrgDetail slug={slug} onBack={() => undefined} onDeleted={onDeleted} />;

describe("организации в админке: демо-API", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(() => {
    activateServerScenario("admin_ready");
  });

  it("ответы проходят схемы контракта", async () => {
    const orgs = (await call("GET", "/orgs")).data as unknown[];
    expect(orgs).toHaveLength(3);
    for (const o of orgs) AdminOrgSchema.parse(o);
    const members = (await call("GET", "/orgs/msp-2025/members"))
      .data as unknown[];
    for (const x of members) AdminOrgMemberSchema.parse(x);
    const groups = (await call("GET", "/orgs/msp-2025/groups"))
      .data as unknown[];
    for (const g of groups) AdminGroupSchema.parse(g);
  });

  it("админ организации видит только свои, чужую организацию не открыть", async () => {
    activateServerScenario("org_admin");
    const orgs = (await call("GET", "/orgs")).data as { slug: string }[];
    expect(orgs.map((o) => o.slug).sort()).toEqual(["ai-lab", "msp-2025"]);
    expect((await call("GET", "/orgs/pilot-2026")).status).toBe(404);
    expect((await call("GET", "/orgs/pilot-2026/members")).status).toBe(404);
    expect((await call("POST", "/orgs", { name: "X", slug: "x" })).status).toBe(
      403,
    );
    expect((await call("DELETE", "/orgs/ai-lab")).status).toBe(403);
  });

  it("студент без ролей админа получает 404, аноним 401", async () => {
    activateServerScenario("student_ready");
    expect((await call("GET", "/orgs")).status).toBe(404);
  });

  it("матрица ролей: админ организации не трогает владельцев", async () => {
    activateServerScenario("org_admin");
    const owner = "u_01hx7k1a0b";
    expect(
      (
        await call("PATCH", `/orgs/msp-2025/members/${owner}`, {
          role: "member",
        })
      ).status,
    ).toBe(403);
    expect(
      (await call("DELETE", `/orgs/msp-2025/members/${owner}`)).status,
    ).toBe(403);
    expect(
      (
        await call("POST", "/orgs/msp-2025/members", {
          email: "maria.keller@example.org",
          role: "owner",
        })
      ).status,
    ).toBe(403);
    const added = await call("POST", "/orgs/msp-2025/members", {
      email: "maria.keller@example.org",
      role: "member",
    });
    expect(added.status).toBe(201);
  });

  it("последнего владельца не понизить и не убрать", async () => {
    const owner = "u_01hx7k1a0b";
    const demote = await call("PATCH", `/orgs/pilot-2026/members/${owner}`, {
      role: "admin",
    });
    expect(demote.status).toBe(409);
    expect(codeOf(demote)).toBe("last_owner");
    const remove = await call("DELETE", `/orgs/pilot-2026/members/${owner}`);
    expect(codeOf(remove)).toBe("last_owner");
    // С двумя владельцами первого понизить можно.
    await call("PATCH", "/orgs/msp-2025/members/u_01hx7k3e5f", {
      role: "owner",
    });
    expect(
      (
        await call("PATCH", `/orgs/msp-2025/members/${owner}`, {
          role: "admin",
        })
      ).status,
    ).toBe(200);
  });

  it("добавление: неизвестный адрес, повтор и неверная роль", async () => {
    const add = (email: string, role: string) =>
      call("POST", "/orgs/msp-2025/members", { email, role });
    expect((await add("nobody@example.org", "member")).status).toBe(404);
    const again = await add("anna.petrova@example.org", "member");
    expect(codeOf(again)).toBe("already_member");
    expect((await add("maria.keller@example.org", "boss")).status).toBe(422);
  });

  it("организация: адрес, зарезервированные имена, повтор и удаление с проектами", async () => {
    const create = (name: string, slug: string) =>
      call("POST", "/orgs", { name, slug });
    expect(codeOf(await create("X", "Bad Slug"))).toBe("slug_invalid");
    expect(codeOf(await create("X", "admin"))).toBe("slug_reserved");
    expect(codeOf(await create("X", "msp-2025"))).toBe("slug_taken");
    expect((await create("", "ok-slug")).status).toBe(422);
    const made = await create("Новая", "novaya");
    expect(made.status).toBe(201);
    expect(AdminOrgSchema.parse(made.data).my_role).toBe("owner");
    expect(codeOf(await call("DELETE", "/orgs/msp-2025"))).toBe(
      "org_has_projects",
    );
    expect((await call("DELETE", "/orgs/novaya")).status).toBe(204);
  });

  it("группы: состав только из участников, уход из организации чистит группы", async () => {
    const bad = await call("POST", "/orgs/ai-lab/groups", {
      name: "Команда",
      member_ids: ["u_01hx7k4p6g"],
    });
    expect(bad.status).toBe(422);
    await call("DELETE", "/orgs/msp-2025/members/u_01hx7k2m9c");
    const groups = (await call("GET", "/orgs/msp-2025/groups")).data as {
      id: string;
    }[];
    for (const g of groups) {
      const page = (await call("GET", `/orgs/msp-2025/groups/${g.id}/members`))
        .data as { items: { user_id: string }[] };
      expect(page.items.map((m) => m.user_id)).not.toContain("u_01hx7k2m9c");
    }
  });

  it("списки по контракту: страница, поиск, сортировка и 422", async () => {
    const page = (
      await call("GET", "/orgs", undefined, {
        limit: "1",
        offset: "0",
        sort: "-member_count",
      })
    ).data as { items: { slug: string }[]; total: number };
    expect(page.total).toBe(3);
    expect(page.items).toHaveLength(1);
    expect(page.items[0]?.slug).toBe("msp-2025");
    const bad = await call("GET", "/orgs", undefined, { sort: "nope" });
    expect(bad.status).toBe(422);
    const members = (
      await call("GET", "/orgs/pilot-2026/members", undefined, { limit: "10" })
    ).data as { items: { is_last_owner: boolean }[] };
    expect(members.items[0]?.is_last_owner).toBe(true);
    const facets = (await call("GET", "/orgs/msp-2025/members/facets"))
      .data as { role: Record<string, number> };
    expect(facets.role.owner).toBe(1);
  });

  it("состав группы меняется по одному человеку", async () => {
    const group = (
      (await call("GET", "/orgs/msp-2025/groups")).data as { id: string }[]
    )[0];
    const id = group?.id ?? "";
    const path = `/orgs/msp-2025/groups/${id}/members/u_01hx7k6r8j`;
    expect((await call("POST", path)).status).toBe(201);
    expect(codeOf(await call("POST", path))).toBe("already_member");
    expect((await call("DELETE", path)).status).toBe(204);
    expect((await call("DELETE", path)).status).toBe(404);
  });
});

describe("организации в админке: экраны", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOrgsLocales();
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("список: строки, поиск и открытие организации", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(wrap(<OrgsList onOpen={onOpen} />));
    expect(await screen.findByTestId("org-open-msp-2025")).toBeVisible();
    expect(screen.getByTestId("org-open-pilot-2026")).toBeVisible();
    await user.type(screen.getByRole("searchbox"), "лаб");
    await waitFor(() => {
      expect(screen.queryByTestId("org-open-msp-2025")).toBeNull();
    });
    await user.click(screen.getByTestId("org-open-ai-lab"));
    expect(onOpen).toHaveBeenCalledWith("ai-lab");
  });

  it("админ организации не видит чужих и кнопки создания", async () => {
    activateServerScenario("org_admin");
    render(wrap(<OrgsList onOpen={() => undefined} />));
    expect(await screen.findByTestId("org-open-msp-2025")).toBeVisible();
    expect(screen.queryByTestId("org-open-pilot-2026")).toBeNull();
    expect(screen.queryByTestId("org-create")).toBeNull();
  });

  it("пустой список: призыв создать первую организацию", async () => {
    activateServerScenario("admin_no_orgs");
    render(wrap(<OrgsList onOpen={() => undefined} />));
    expect(await screen.findByText("Организаций пока нет")).toBeVisible();
    expect(screen.getByTestId("org-create")).toBeVisible();
  });

  it("создание: адрес из названия, отказ занятого адреса, успех открывает организацию", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(wrap(<OrgsList onOpen={onOpen} />));
    await user.click(await screen.findByTestId("org-create"));
    await user.type(screen.getByTestId("org-create-name"), "МСПИН 2025");
    expect(screen.getByTestId("org-create-slug")).toHaveValue("mspin-2025");
    await user.clear(screen.getByTestId("org-create-slug"));
    await user.type(screen.getByTestId("org-create-slug"), "msp-2025");
    await user.click(screen.getByTestId("org-create-submit"));
    expect(
      await screen.findByText("Такой адрес уже занят другой организацией."),
    ).toBeVisible();
    await user.clear(screen.getByTestId("org-create-slug"));
    await user.type(screen.getByTestId("org-create-slug"), "mspin-2026");
    await user.click(screen.getByTestId("org-create-submit"));
    await waitFor(() => {
      expect(onOpen).toHaveBeenCalledWith("mspin-2026");
    });
  });

  it("создание: пустое название и неверный адрес не уходят на сервер", async () => {
    const user = userEvent.setup();
    render(wrap(<OrgsList onOpen={() => undefined} />));
    await user.click(await screen.findByTestId("org-create"));
    await user.click(screen.getByTestId("org-create-submit"));
    expect(screen.getByText("Введите название.")).toBeVisible();
    expect(screen.getByText(/Введите адрес/)).toBeVisible();
  });

  it("вкладки: числа, проекты и настройки организации", async () => {
    const user = userEvent.setup();
    render(wrap(<Detail slug="msp-2025" />));
    const members = await screen.findByTestId("org-tab-members");
    expect(members).toHaveAttribute("aria-selected", "true");
    expect(members).toHaveTextContent("6");
    await waitFor(() => {
      expect(screen.getByTestId("org-tab-groups")).toHaveTextContent("2");
    });
    // Проектов во вкладках нет: число стоит в шапке.
    expect(screen.queryByTestId("org-tab-projects")).toBeNull();
    expect(screen.getByTestId("org-projects")).toHaveTextContent("31 проект");
    await user.click(screen.getByTestId("org-tab-settings"));
    const settings = await screen.findByTestId("org-settings");
    expect(within(settings).getByDisplayValue("msp-2025")).toBeVisible();
    expect(within(settings).getByTestId("org-danger")).toBeVisible();
  });

  it("админ организации не видит опасной зоны", async () => {
    const user = userEvent.setup();
    activateServerScenario("org_admin");
    render(wrap(<Detail slug="msp-2025" />));
    await user.click(await screen.findByTestId("org-tab-settings"));
    expect(await screen.findByTestId("org-settings")).toBeVisible();
    expect(screen.queryByTestId("org-delete")).toBeNull();
  });

  it("чужая организация выглядит как несуществующая", async () => {
    activateServerScenario("org_admin");
    render(wrap(<Detail slug="pilot-2026" />));
    expect(await screen.findByTestId("org-missing")).toBeVisible();
  });

  it("участники: единственный владелец защищён, добавление и отказы", async () => {
    activateServerScenario("admin_ready");
    const user = userEvent.setup();
    render(wrap(<Detail slug="pilot-2026" />));
    expect(
      await screen.findByTestId("member-last-owner-u_01hx7k1a0b"),
    ).toBeVisible();
    // У единственного владельца нет меню действий: убрать его нельзя.
    expect(screen.queryByTestId("member-actions-u_01hx7k1a0b")).toBeNull();
    expect(screen.queryByTestId("member-role-u_01hx7k1a0b")).toBeNull();

    await user.click(screen.getByTestId("member-add-open"));
    // Админ установки выбирает человека поиском; почта остаётся запасным путём.
    expect(screen.getByTestId("member-add-person")).toBeVisible();
    await user.click(screen.getByTestId("member-add-mode"));
    await user.type(
      screen.getByTestId("member-add-email"),
      "nobody@example.org",
    );
    await user.click(screen.getByTestId("member-add-submit"));
    expect(
      await screen.findByText(/Человека с таким адресом нет/),
    ).toBeVisible();

    await user.clear(screen.getByTestId("member-add-email"));
    await user.type(
      screen.getByTestId("member-add-email"),
      "maria.keller@example.org",
    );
    await user.click(screen.getByTestId("member-add-submit"));
    expect(await screen.findByText("Мария Келлер")).toBeVisible();
    // После добавления окно закрывается, при следующем открытии поле пустое.
    await waitFor(() => {
      expect(screen.queryByTestId("member-add-email")).toBeNull();
    });
    await user.click(screen.getByTestId("member-add-open"));
    await user.click(screen.getByTestId("member-add-mode"));
    expect(screen.getByTestId("member-add-email")).toHaveValue("");

    await user.type(
      screen.getByTestId("member-add-email"),
      "maria.keller@example.org",
    );
    await user.click(screen.getByTestId("member-add-submit"));
    expect(
      await screen.findByText("Этот человек уже в организации."),
    ).toBeVisible();

    // Неверный адрес снимает прошлый отказ сервера: на экране одно сообщение.
    await user.clear(screen.getByTestId("member-add-email"));
    await user.type(screen.getByTestId("member-add-email"), "не-адрес");
    await user.click(screen.getByTestId("member-add-submit"));
    expect(await screen.findByText("Введите адрес почты.")).toBeVisible();
    expect(screen.queryByText("Этот человек уже в организации.")).toBeNull();
  }, 20_000);

  it("участники: выбор человека поиском добавляет его по id", async () => {
    const user = userEvent.setup();
    render(wrap(<Detail slug="pilot-2026" />));
    await user.click(await screen.findByTestId("member-add-open"));
    await user.click(screen.getByTestId("member-add-person"));
    await user.type(
      screen.getByRole("combobox", { name: "Человек" }),
      "келлер",
    );
    await user.click(
      await screen.findByRole("option", { name: /Мария Келлер/ }),
    );
    await user.click(screen.getByTestId("member-add-submit"));
    expect(await screen.findByText("Мария Келлер")).toBeVisible();
  }, 20_000);

  it("участники: фильтр по роли с числами с сервера", async () => {
    const user = userEvent.setup();
    render(wrap(<Detail slug="msp-2025" />));
    await screen.findByText("Дмитрий Кузнецов");
    await user.click(screen.getByTestId("members-filter-role"));
    const owner = await screen.findByRole("checkbox", {
      name: /Владелец/,
    });
    await waitFor(() => {
      expect(owner).toHaveTextContent("1");
    });
    await user.click(owner);
    await waitFor(() => {
      expect(screen.queryByText("Дмитрий Кузнецов")).toBeNull();
    });
  });

  it("участники: удаление требует подтверждения", async () => {
    const user = userEvent.setup();
    render(wrap(<Detail slug="msp-2025" />));
    await user.click(await screen.findByTestId("member-actions-u_01hx7k6r8j"));
    await user.click(await screen.findByTestId("member-remove-u_01hx7k6r8j"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/потеряет доступ/)).toBeVisible();
    await user.click(within(dialog).getByTestId("member-remove-confirm"));
    await waitFor(() => {
      expect(screen.queryByText("Дмитрий Кузнецов")).toBeNull();
    });
  });

  it("группы: создание с составом, правка и удаление", async () => {
    const user = userEvent.setup();
    render(wrap(<Detail slug="ai-lab" />));
    await user.click(await screen.findByTestId("org-tab-groups"));
    expect(await screen.findByTestId("groups-empty")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Создать группу" }));
    const form = await screen.findByTestId("group-form");
    await user.click(within(form).getByTestId("group-save"));
    expect(within(form).getByText("Введите название.")).toBeVisible();
    await user.type(within(form).getByTestId("group-name"), "Проект");
    await user.click(within(form).getByTestId("group-add-person"));
    await user.click(
      await screen.findByRole("option", { name: /Дмитрий Кузнецов/ }),
    );
    expect(within(form).getByTestId("group-chosen")).toHaveTextContent(
      "Дмитрий Кузнецов",
    );
    await user.click(within(form).getByTestId("group-save"));
    expect(await screen.findByText("Проект")).toBeVisible();
    expect(screen.getByText("1 человек")).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Удалить группу Проект" }),
    );
    await user.click(await screen.findByTestId("group-delete-confirm"));
    expect(await screen.findByTestId("groups-empty")).toBeVisible();
  }, 20_000);

  it("удаление организации: с проектами кнопка выключена, без проектов уходит", async () => {
    const user = userEvent.setup();
    const first = render(wrap(<Detail slug="msp-2025" />));
    await user.click(await screen.findByTestId("org-tab-settings"));
    expect(await screen.findByTestId("org-delete")).toBeDisabled();
    expect(screen.getByText(/с проектами сервер откажет/)).toBeVisible();
    first.unmount();

    const onDeleted = vi.fn();
    render(wrap(<Detail slug="pilot-2026" onDeleted={onDeleted} />));
    await user.click(await screen.findByTestId("org-tab-settings"));
    await user.click(await screen.findByTestId("org-delete"));
    await user.type(
      screen.getByRole("textbox", { name: /Пилот 2026/ }),
      "Пилот 2026",
    );
    await user.click(
      screen.getByRole("button", { name: "Удалить организацию" }),
    );
    await waitFor(() => {
      expect(onDeleted).toHaveBeenCalled();
    });
  }, 20_000);

  it("английский интерфейс", async () => {
    await i18n.changeLanguage("en");
    render(wrap(<OrgsList onOpen={() => undefined} />));
    expect(await screen.findByText("Organizations")).toBeVisible();
    expect(await screen.findByText("Create organization")).toBeVisible();
    await i18n.changeLanguage("ru");
  });
});

describe("организации: чистая логика", () => {
  it("адрес из названия", () => {
    expect(slugify("МСПИН 2025")).toBe("mspin-2025");
    expect(slugify("  Лаборатория ИИ!  ")).toBe("laboratoriya-ii");
    expect(slugify("---")).toBe("");
    expect(isValidSlug("msp-2025")).toBe(true);
    expect(isValidSlug("-msp")).toBe(false);
    expect(isValidSlug("Msp")).toBe(false);
    expect(isValidSlug("")).toBe(false);
  });

  it("права по ролям", () => {
    const full = { instanceAdmin: true, role: null } as const;
    const admin = { instanceAdmin: false, role: "admin" } as const;
    expect(assignableRoles(full)).toContain("owner");
    expect(assignableRoles(admin)).not.toContain("owner");
    expect(canEditMember(admin, "owner")).toBe(false);
    expect(canEditMember(admin, "member")).toBe(true);
    const owner = {
      user_id: "a",
      name: "A",
      email: "a@x.org",
      role: "owner",
      joined_at: "",
    } as const;
    expect(isLastOwner(owner, 2)).toBe(false);
    expect(isLastOwner(owner, 1)).toBe(true);
    // Строка по контракту несёт признак сама; без данных замка нет.
    expect(isLastOwner({ ...owner, is_last_owner: true }, 5)).toBe(true);
    expect(isLastOwner(owner)).toBe(false);
  });

  it("локаль подключается один раз", async () => {
    const first = ensureAdminOrgsLocales();
    expect(ensureAdminOrgsLocales()).toBe(first);
    await first;
    expect(i18n.hasResourceBundle("ru", "adminOrgs")).toBe(true);
  });
});
