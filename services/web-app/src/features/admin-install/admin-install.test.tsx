import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { createDemoRouter } from "@shared/api/demo";
import type { DemoRequest } from "@shared/api/demo";
import { AIProviderSchema } from "@entities/ai-provider";
import {
  AdminAiProviderSchema,
  AdminBuildSettingsSchema,
  AdminInstanceSettingsSchema,
  AdminSigningPolicySchema,
} from "@entities/session";
import { installServerDemo } from "@/app/demo";
import { activateServerScenario } from "@/app/demo/server";
import {
  getServerWorld,
  serverAdminDemoRoutes,
  serverDemoRoutes,
} from "@/app/demo/server/routes";
import { SigningIdentitiesSection } from "@widgets/settings/sections/SigningIdentitiesSection";
import { AiProvidersPage, InstancePage, SigningPolicyPage } from "./index";
import { isInsecureUrl, isPublicUrl, validateInstance } from "./lib/validate";

// Настройки установки поверх демо-транспорта: те же запросы, что уйдут настоящему
// бэкенду, и ответы, проходящие те же схемы.

const client = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

const mount = (node: ReactNode) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client()}>
        <MemoryRouter>{node}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

const makeCall =
  (routes: typeof serverAdminDemoRoutes) =>
  async (method: DemoRequest["method"], path: string, body?: unknown) => {
    const found = createDemoRouter(routes).match(method, path);
    if (!found) throw new Error(`no demo route ${method} ${path}`);
    return found.handler({
      method,
      path,
      params: found.params,
      query: {},
      body,
      forward: () => Promise.reject(new Error("forward")),
    });
  };
const call = makeCall(serverAdminDemoRoutes);
const callUser = makeCall(serverDemoRoutes);

const noEditor = () => null;

describe("настройки установки в админке", () => {
  beforeAll(() => {
    installServerDemo();
  });
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    activateServerScenario("admin_ready");
  });
  afterEach(cleanup);

  it("ответы демо проходят схемы контракта и не содержат ключей", async () => {
    AdminInstanceSettingsSchema.parse(
      (await call("GET", "/settings/instance")).data,
    );
    AdminBuildSettingsSchema.parse((await call("GET", "/settings/build")).data);
    AdminSigningPolicySchema.parse(
      (await call("GET", "/settings/signing")).data,
    );
    const providers = (await call("GET", "/ai-providers")).data as unknown[];
    for (const p of providers) AdminAiProviderSchema.parse(p);
    expect(JSON.stringify(providers)).not.toContain('"api_key"');
  });

  it("не-админу /api/admin отвечает 404", async () => {
    activateServerScenario("student_ready");
    expect((await call("GET", "/settings/instance")).status).toBe(404);
    expect((await call("GET", "/ai-providers")).status).toBe(404);
  });

  describe("название и адрес", () => {
    it("проверка адреса и предупреждение про http", () => {
      expect(isPublicUrl("https://studio.example.org")).toBe(true);
      expect(isPublicUrl("http://localhost:8080")).toBe(true);
      expect(isPublicUrl("http://studio.example.org")).toBe(false);
      expect(isPublicUrl("https://studio.example.org/?x=1")).toBe(false);
      expect(isInsecureUrl("http://localhost:8080")).toBe(true);
      expect(
        validateInstance({ name: " ", public_url: "x", docs_url: "ftp://a" }),
      ).toEqual({
        name: "name_required",
        public_url: "url_invalid",
        docs_url: "docs_invalid",
      });
    });

    it("заданное окружением только читается, остальное сохраняется", async () => {
      activateServerScenario("install_env_locked");
      const user = userEvent.setup();
      mount(<InstancePage />);
      const form = await screen.findByTestId("instance-form");
      expect(within(form).getByLabelText("Публичный адрес")).toHaveAttribute(
        "readonly",
      );
      expect(screen.getByTestId("locked-instance-public_url")).toBeVisible();
      const name = within(form).getByLabelText("Название установки");
      expect(name).not.toHaveAttribute("readonly");
      await user.clear(name);
      await user.type(name, "Studio кафедры");
      await user.click(screen.getByTestId("instance-save"));
      expect(await screen.findByTestId("instance-saved")).toBeVisible();
      const saved = (await call("GET", "/settings/instance")).data as {
        name: string;
        public_url: string;
      };
      expect(saved.name).toBe("Studio кафедры");
      expect(saved.public_url).toBe("https://studio.hse.example");
    });

    it("неверный адрес показывает ошибку и ничего не отправляет", async () => {
      const user = userEvent.setup();
      mount(<InstancePage />);
      const url = await screen.findByLabelText("Публичный адрес");
      await user.clear(url);
      await user.type(url, "http://studio.example.org");
      await user.click(screen.getByTestId("instance-save"));
      expect(await screen.findByText(/Нужен адрес вида https/)).toBeVisible();
      expect(
        (
          (await call("GET", "/settings/instance")).data as {
            public_url: string;
          }
        ).public_url,
      ).toBe("https://studio.example.org");
    });

    it("смена адреса предупреждает о ссылках", async () => {
      const user = userEvent.setup();
      mount(<InstancePage />);
      const url = await screen.findByLabelText("Публичный адрес");
      await user.clear(url);
      await user.type(url, "https://new.example.org");
      expect(screen.getByTestId("instance-url-impact")).toBeVisible();
    });

    it("сервер отвечает 409 на закрытое окружением поле", async () => {
      activateServerScenario("install_env_locked");
      const res = await call("PUT", "/settings/instance", {
        name: null,
        public_url: "https://x.example.org",
        docs_url: null,
      });
      expect(res.status).toBe(409);
    });
  });

  describe("сборка", () => {
    it("предел вне диапазона не отправляется, верный уходит в секундах", async () => {
      const user = userEvent.setup();
      mount(<InstancePage />);
      const form = await screen.findByTestId("build-form");
      const timeout = within(form).getByLabelText(/Предел длительности/);
      await user.clear(timeout);
      await user.type(timeout, "99");
      await user.click(screen.getByTestId("build-save"));
      expect(
        await within(form).findAllByText(/Целое число от 1 до 60/),
      ).not.toHaveLength(0);
      await user.clear(timeout);
      await user.type(timeout, "10");
      await user.click(screen.getByTestId("build-save"));
      expect(await screen.findByTestId("build-saved")).toBeVisible();
      expect(
        ((await call("GET", "/settings/build")).data as { timeout_s: number })
          .timeout_s,
      ).toBe(600);
    });

    it("предел из окружения закрыт", async () => {
      activateServerScenario("install_env_locked");
      mount(<InstancePage />);
      const form = await screen.findByTestId("build-form");
      expect(
        within(form).getByLabelText(/Предел длительности/),
      ).toHaveAttribute("readonly");
      expect(screen.getByTestId("locked-build-timeout")).toBeVisible();
    });
  });

  describe("политика ключей подписи", () => {
    it("переключатель: предупреждения и сохранение меняют возможности пользователя", async () => {
      const user = userEvent.setup();
      mount(<SigningPolicyPage />);
      const toggle = await screen.findByTestId("signing-toggle");
      expect(toggle).toBeChecked();
      expect(screen.getByTestId("signing-state")).toHaveTextContent(
        "Хранение разрешено",
      );
      await user.click(toggle);
      // Два ключа уже лежат на сервере: при выключении они остаются, но блокируются.
      expect(screen.getByTestId("signing-warn-off")).toHaveTextContent(
        /Сохранённые ключи \(2\) останутся на сервере/,
      );
      expect(
        getServerWorld().bootstrap.capabilities.personal_signing_keys,
      ).toBe(true);
      await user.click(screen.getByTestId("signing-save"));
      expect(await screen.findByTestId("signing-saved")).toBeVisible();
      expect(screen.getByTestId("signing-state")).toHaveTextContent(
        "Хранение запрещено",
      );
      expect(screen.getByTestId("signing-blocked")).toBeVisible();
      expect(
        getServerWorld().bootstrap.capabilities.personal_signing_keys,
      ).toBe(false);
      // Включение снова: предупреждение о рисках.
      await user.click(screen.getByTestId("signing-toggle"));
      expect(screen.getByText(/смогут хранить секретные ключи/)).toBeVisible();
    });

    it("политика окружения только читается", async () => {
      activateServerScenario("install_env_locked");
      mount(<SigningPolicyPage />);
      const toggle = await screen.findByTestId("signing-toggle");
      expect(toggle).toBeDisabled();
      expect(screen.getByTestId("locked-signing")).toBeVisible();
      expect(screen.queryByTestId("signing-save")).toBeNull();
      const res = await call("PUT", "/settings/signing", {
        server_keys: "allowed",
      });
      expect(res.status).toBe(409);
    });

    it("запрет не стирает ключи", async () => {
      await call("PUT", "/settings/signing", { server_keys: "forbidden" });
      const policy = (await call("GET", "/settings/signing")).data as {
        stored_keys: number;
        server_keys: string;
      };
      expect(policy).toMatchObject({
        server_keys: "forbidden",
        stored_keys: 2,
      });
    });
  });

  describe("раздел «Подпись» пользователя", () => {
    it("при запрете показывает пояснение вместо форм", async () => {
      activateServerScenario("install_env_locked");
      await call("GET", "/settings/signing");
      // Политика закрыта окружением, а вошедший человек видит её последствия.
      mount(<SigningIdentitiesSection />);
      const note = await screen.findByTestId("signing-forbidden");
      expect(note).toHaveTextContent("Сервер не хранит секретные ключи");
      expect(screen.queryByText("Самоподписанный")).toBeNull();
    });
  });

  describe("общие ИИ-провайдеры", () => {
    it("создание: ключ принимается, но не возвращается", async () => {
      const created = await call("POST", "/ai-providers", {
        name: "Новый",
        type: "openai",
        api_key: "sk-secret-123",
        base_url: "",
        models: [],
        ssl_verify: true,
        connect_timeout_s: 10,
        request_timeout_s: 60,
      });
      expect(created.status).toBe(201);
      const body = created.data as Record<string, unknown>;
      AdminAiProviderSchema.parse(body);
      expect(body.has_api_key).toBe(true);
      expect(JSON.stringify(body)).not.toContain("sk-secret-123");
      expect(
        JSON.stringify((await call("GET", "/ai-providers")).data),
      ).not.toContain("sk-secret-123");
    });

    it("без ключа создать нельзя", async () => {
      const res = await call("POST", "/ai-providers", {
        name: "Без ключа",
        type: "claude",
        api_key: "",
      });
      expect(res.status).toBe(422);
    });

    it("пользователь видит общий провайдер без ключа и с пометкой", async () => {
      activateServerScenario("student_ready");
      const res = await callUser("GET", "/ai-providers");
      const list = res.data as Record<string, unknown>[];
      expect(list.length).toBeGreaterThan(0);
      for (const item of list) {
        AIProviderSchema.parse(item);
        expect(item.shared).toBe(true);
        expect(item).not.toHaveProperty("api_key");
      }
    });

    it("список: провайдер без ключа помечен, с ключом не показывает его", async () => {
      mount(<AiProvidersPage renderEditor={noEditor} />);
      const withKey = await screen.findByTestId("shared-provider-aip_shared1");
      expect(within(withKey).getByTestId("provider-key-set")).toBeVisible();
      expect(withKey).toHaveTextContent("общий");
      const noKey = screen.getByTestId("shared-provider-aip_shared2");
      expect(within(noKey).getByTestId("provider-key-missing")).toBeVisible();
      expect(document.body.textContent).not.toMatch(/sk-/);
    });

    it("пустой список объясняет, что делать", async () => {
      activateServerScenario("install_fresh");
      mount(<AiProvidersPage renderEditor={noEditor} />);
      expect(await screen.findByTestId("shared-provider-empty")).toBeVisible();
    });

    it("добавление открывает редактор из слота, удаление просит подтверждения", async () => {
      const user = userEvent.setup();
      mount(
        <AiProvidersPage
          renderEditor={({ provider }) => (
            <div data-testid="editor-slot">{provider?.name ?? "новый"}</div>
          )}
        />,
      );
      await user.click(await screen.findByTestId("shared-provider-add"));
      expect(screen.getByTestId("editor-slot")).toHaveTextContent("новый");

      await user.click(
        screen.getByRole("button", { name: "Удалить провайдера Общий Claude" }),
      );
      expect(screen.getByTestId("shared-provider-delete")).toHaveTextContent(
        "Общий Claude",
      );
      await user.click(screen.getByTestId("shared-provider-delete-confirm"));
      await waitFor(() => {
        expect(screen.queryByTestId("shared-provider-aip_shared1")).toBeNull();
      });
    });
  });
});
