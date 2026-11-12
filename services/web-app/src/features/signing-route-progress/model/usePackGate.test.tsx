import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import {
  signingRouteApi,
  type SigningRouteStatus,
} from "@entities/signing-route";
import { makeSigningRouteSummary } from "@entities/signing-route/testing";
import { i18n } from "@shared/lib";
import { usePackGate } from "./usePackGate";

const PROJECT = "p1";

type Plan = Awaited<ReturnType<typeof signatureApi.getPlan>>;

const plan = (signed: number, total: number): Plan => ({
  profile_id: "topic",
  total,
  signed,
  crypto_total: 0,
  crypto_signed: 0,
  waiting_for_me: 0,
  docs: [],
  route: null,
});

const serverBoot = () =>
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
    ...LOCAL_BOOTSTRAP,
    mode: "server",
    user: {
      id: "u1",
      name: "Иванов И. И.",
      email: "ivanov@edu.hse.ru",
      avatar_initials: "ИИ",
      is_instance_admin: false,
      email_verified: true,
      locale: null,
      org_roles: [],
    },
  });

const routes = (status: SigningRouteStatus | null) =>
  vi.spyOn(signingRouteApi, "list").mockResolvedValue({
    items:
      status === null
        ? []
        : [
            makeSigningRouteSummary({
              status,
              phase: status === "active" ? "approval" : null,
              current_step: status === "active" ? 3 : null,
              steps_total: 3,
              waiting_for:
                status === "active"
                  ? [{ name: "Сидоров С. С.", persona: "academic_supervisor" }]
                  : [],
            }),
          ],
  });

const wrapper = ({ children }: { children: ReactNode }) => (
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>
  </I18nextProvider>
);

const gate = () =>
  renderHook(
    () =>
      usePackGate({
        project: { id: PROJECT },
        profileId: "topic",
        author: null,
      }),
    { wrapper },
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("готовность пакета: маршрут подписания и подписи", () => {
  it("маршрут идёт, подписи не готовы: сборка выключена, строка называет, кого ждём", async () => {
    serverBoot();
    routes("active");
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(2, 3));

    const { result } = gate();

    await waitFor(() => {
      expect(result.current.rows).toHaveLength(1);
    });
    expect(result.current.blocked).toBe(true);
    const [row] = result.current.rows;
    expect(row).toMatchObject({
      key: "route",
      tone: "err",
      link: "/projects/p1/submit/cp/topic#signing-route",
    });
    expect(row?.text).toBe(
      "Маршрут подписания не завершён (шаг 3 из 3). Сейчас ждём: Академический руководитель Сидоров С. С.",
    );
    expect(result.current.reason).toBe(row?.text);
  });

  it("маршрут идёт, но обязательные подписи готовы: только предупреждение", async () => {
    serverBoot();
    routes("active");
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(3, 3));

    const { result } = gate();

    await waitFor(() => {
      expect(result.current.rows[0]?.tone).toBe("warn");
    });
    expect(result.current.blocked).toBe(false);
    expect(result.current.reason).toBeNull();
    expect(result.current.rows[0]?.text).toContain("пакет можно собрать");
  });

  it("маршрут идёт, а плана нет: сборка выключена, как ответит сервер", async () => {
    serverBoot();
    routes("active");
    vi.spyOn(signatureApi, "getPlan").mockRejectedValue(new Error("boom"));

    const { result } = gate();

    await waitFor(() => {
      expect(result.current.rows).toHaveLength(1);
    });
    expect(result.current.blocked).toBe(true);
  });

  it.each([
    ["paused", "Маршрут подписания остановлен."],
    ["returned", "Документы вернули на доработку."],
  ] as const)(
    "маршрут %s: причина и ссылка на карточку «Подписание»",
    async (status, start) => {
      serverBoot();
      routes(status);
      vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(1, 3));

      const { result } = gate();

      await waitFor(() => {
        expect(result.current.rows).toHaveLength(1);
      });
      expect(result.current.blocked).toBe(true);
      expect(result.current.rows[0]?.text.startsWith(start)).toBe(true);
      expect(result.current.rows[0]?.link).not.toBeNull();
    },
  );

  it("без маршрута подписи не готовы: строка со счётом, сборка выключена", async () => {
    serverBoot();
    routes(null);
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(1, 3));

    const { result } = gate();

    await waitFor(() => {
      expect(result.current.blocked).toBe(true);
    });
    expect(result.current.rows).toEqual([
      {
        key: "signatures",
        tone: "err",
        text: "Готовы не все подписи: 1 из 3. Чего не хватает, видно в списке документов точки.",
        link: null,
      },
    ]);
  });

  it("завершённый маршрут и все подписи: строк нет, сборка доступна", async () => {
    serverBoot();
    routes("completed");
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(3, 3));

    const { result } = gate();

    await waitFor(() => {
      expect(signatureApi.getPlan).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(result.current.blocked).toBe(false);
    });
    expect(result.current.rows).toEqual([]);
  });

  it("локальная Студия: маршрутов не спрашивает, считает по плану", async () => {
    vi.spyOn(sessionApi, "bootstrap").mockResolvedValue(LOCAL_BOOTSTRAP);
    const list = routes("active");
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(0, 2));

    const { result } = gate();

    await waitFor(() => {
      expect(result.current.rows[0]?.key).toBe("signatures");
    });
    expect(list).not.toHaveBeenCalled();
  });
});
