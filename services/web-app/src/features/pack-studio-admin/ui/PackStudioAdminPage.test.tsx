import { readFileSync } from "node:fs";
import { join } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import {
  PackServiceAccessCheckSchema,
  PackServiceAccessListSchema,
  PackServiceAccessSchema,
  PackStudioAdminSchema,
  PackStudioOfficialAdminSchema,
  packStudioApi,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n, loadAdminNamespaces } from "@shared/lib";
import { PackStudioAdminPage } from "./PackStudioAdminPage";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-studio/fixtures/PackStudioAdmin",
);
const admin = (name: string) =>
  PackStudioAdminSchema.parse(
    JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), "utf8")),
  );

const SERVICE = PackServiceAccessListSchema.parse(
  JSON.parse(
    readFileSync(
      join(FIXTURES, "..", "PackServiceAccessList", "one.json"),
      "utf8",
    ),
  ),
);

const fixtureOf = <T,>(
  schema: { parse: (raw: unknown) => T },
  dir: string,
  name: string,
): T =>
  schema.parse(
    JSON.parse(readFileSync(join(FIXTURES, "..", dir, `${name}.json`), "utf8")),
  );
const NO_BOT = fixtureOf(
  PackStudioOfficialAdminSchema,
  "PackStudioOfficialAdmin",
  "no_bot",
);
const BOT = fixtureOf(
  PackServiceAccessSchema,
  "PackServiceAccess",
  "github_bot",
);
const FINE_GRAINED = fixtureOf(
  PackServiceAccessCheckSchema,
  "PackServiceAccessCheck",
  "fine_grained",
);

const mount = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <PackStudioAdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("админка: Студия шаблонов", () => {
  beforeAll(async () => {
    await loadAdminNamespaces(["packStudio"]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    vi.spyOn(packStudioApi, "officialAdmin").mockResolvedValue(NO_BOT);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });
  const noService = () =>
    vi.spyOn(packStudioApi, "serviceAccess").mockResolvedValue([]);

  it("включение раздела и права людям и группам, снятие права", async () => {
    const data = admin("enabled");
    noService();
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(data);
    const setAdmin = vi
      .spyOn(packStudioApi, "setAdmin")
      .mockResolvedValue({ ...data, enabled: false });
    const remove = vi.spyOn(packStudioApi, "removeGrant").mockResolvedValue();
    mount();
    const toggle = await screen.findByTestId("ps-admin-enabled");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Анна Петрова")).toBeInTheDocument();
    expect(screen.getByText(/группа · ФКН/)).toBeInTheDocument();

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(setAdmin).toHaveBeenCalledWith(false);
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Снять право у «Анна Петрова»" }),
    );
    expect(remove).toHaveBeenCalledWith(data.grants[0]?.id);
  });

  it("включение из окружения: переключатель закрыт, прав нет", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("locked_off"));
    noService();
    mount();
    expect(await screen.findByTestId("ps-admin-enabled")).toBeDisabled();
    expect(screen.getByText("Право пока никому не выдано")).toBeInTheDocument();
  });

  it("служебные доступы: список без секрета, добавление с токеном, удаление с подтверждением", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("enabled"));
    const list = vi
      .spyOn(packStudioApi, "serviceAccess")
      .mockResolvedValue(SERVICE);
    const add = vi
      .spyOn(packStudioApi, "addServiceAccess")
      .mockResolvedValue(SERVICE[0] ?? ({} as never));
    const remove = vi
      .spyOn(packStudioApi, "removeServiceAccess")
      .mockResolvedValue();
    mount();
    const item = SERVICE[0];
    if (!item) throw new Error("нет эталона");
    const row = await screen.findByTestId(`ps-service-${item.id}`);
    expect(row).toHaveTextContent("fcs/packs");
    expect(row).toHaveTextContent("https://gitlab.hse.ru/fcs/packs.git");
    expect(row).toHaveTextContent("glpat…");

    await userEvent.click(screen.getByTestId("ps-service-open"));
    const submit = screen.getByTestId("ps-service-submit");
    expect(submit).toBeDisabled();
    await userEvent.type(
      screen.getByTestId("ps-service-url"),
      "https://gitlab.hse.ru/fcs/other.git",
    );
    await userEvent.type(screen.getByTestId("ps-service-label"), "Другие");
    await userEvent.type(screen.getByTestId("ps-service-token"), "glpat-1");
    await userEvent.click(submit);
    await waitFor(() => {
      expect(add).toHaveBeenCalledWith({
        url: "https://gitlab.hse.ru/fcs/other.git",
        token: "glpat-1",
        label: "Другие",
      });
    });
    await waitFor(() => {
      expect(list).toHaveBeenCalledTimes(2);
    });

    await userEvent.click(within(row).getByTestId("ps-service-remove"));
    await userEvent.click(screen.getByTestId("ps-service-remove-confirm"));
    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith(item.id);
    });
  });

  it("служебный доступ уже задан: отказ сервера словами", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("enabled"));
    noService();
    vi.spyOn(packStudioApi, "addServiceAccess").mockRejectedValue(
      new ApiError("x", "service_access_exists", 409),
    );
    mount();
    expect(await screen.findByTestId("ps-service-empty")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ps-service-open"));
    await userEvent.type(
      screen.getByTestId("ps-service-url"),
      "https://gitlab.hse.ru/fcs/packs.git",
    );
    await userEvent.type(screen.getByTestId("ps-service-token"), "glpat-1");
    await userEvent.click(screen.getByTestId("ps-service-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "служебный доступ уже задан",
    );
    // Токен не остаётся в окне после запроса.
    expect(screen.getByTestId("ps-service-token")).toHaveValue("");
  });

  it("официальные паки: бот добавляется с адресом репозитория и режимом форка, лимит сохраняется", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("enabled"));
    noService();
    const add = vi
      .spyOn(packStudioApi, "addServiceAccess")
      .mockResolvedValue(BOT);
    const save = vi
      .spyOn(packStudioApi, "setOfficialAdmin")
      .mockResolvedValue({ ...NO_BOT, daily_limit: 3 });
    mount();
    const section = await screen.findByTestId("ps-official");
    expect(section).toHaveTextContent(NO_BOT.repo?.web_url ?? "");
    expect(screen.getByTestId("ps-official-enabled")).toHaveAttribute(
      "aria-checked",
      "false",
    );

    await userEvent.click(screen.getByTestId("ps-official-add-bot"));
    expect(screen.getByTestId("ps-service-url")).toHaveValue(NO_BOT.repo?.url);
    expect(screen.getByTestId("ps-service-fork")).toBeChecked();
    await userEvent.type(screen.getByTestId("ps-service-token"), "ghp_1");
    await userEvent.click(screen.getByTestId("ps-service-submit"));
    await waitFor(() => {
      expect(add).toHaveBeenCalledWith({
        url: NO_BOT.repo?.url,
        token: "ghp_1",
        label: null,
        fork_mode: true,
      });
    });

    const limit = screen.getByTestId("ps-official-limit");
    await userEvent.clear(limit);
    await userEvent.type(limit, "3");
    await userEvent.click(screen.getByTestId("ps-official-limit-save"));
    await waitFor(() => {
      expect(save).toHaveBeenCalledWith({ bot_enabled: false, daily_limit: 3 });
    });
  });

  it("проверка доступа бота: точный токен назван проблемой словами", async () => {
    vi.spyOn(packStudioApi, "admin").mockResolvedValue(admin("enabled"));
    vi.spyOn(packStudioApi, "serviceAccess").mockResolvedValue([BOT]);
    const check = vi
      .spyOn(packStudioApi, "checkServiceAccess")
      .mockResolvedValue(FINE_GRAINED);
    mount();
    const row = await screen.findByTestId(`ps-service-${BOT.id}`);
    expect(row).toHaveTextContent("бот, форк");
    await userEvent.click(within(row).getByTestId("ps-service-check"));
    await waitFor(() => {
      expect(check).toHaveBeenCalledWith(BOT.id);
    });
    expect(
      await screen.findByTestId("ps-service-problem-fine_grained_token"),
    ).toHaveTextContent("public_repo");
    expect(screen.getByTestId("ps-service-check-result")).toHaveTextContent(
      "hse-doc-studio-bot",
    );
  });
});
