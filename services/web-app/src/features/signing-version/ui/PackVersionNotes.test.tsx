import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { documentApi } from "@entities/document";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import { signingRouteApi } from "@entities/signing-route";
import { makeSigningRouteSummary } from "@entities/signing-route/testing";
import { PackWarningSchema, type PackWarning } from "@entities/submission";
import { i18n } from "@shared/lib";
import { PackVersionPreflight, PackVersionWarnings } from "./PackVersionNotes";

const PROJECT = "p1";
const ROUTE = "sr_1";
const SHA = "a".repeat(64);

type Plan = Awaited<ReturnType<typeof signatureApi.getPlan>>;
type Doc = Plan["docs"][number];

const docPlan = (doc_id: string, extra: Partial<Doc> = {}): Doc => ({
  doc_id,
  built: true,
  frozen: null,
  slots: [],
  held_by_route: false,
  pinned: null,
  working_differs: false,
  ...extra,
});

const pinned = {
  sha256: SHA,
  pinned_at: "2026-11-10T11:32:00Z",
  route_id: ROUTE,
  round: 1,
};

const warning: PackWarning = PackWarningSchema.parse({
  code: "changed_after_sent",
  doc_id: "annotation",
  sent_at: "2026-11-10T11:32:00Z",
  file: "Аннотация.pdf",
  message:
    "Документ «Аннотация» изменён после отправки на подпись: в пакет попала версия на подписи от 10.11.2026",
  pinned,
  working_sha256: "b".repeat(64),
});

const serverBoot = () => {
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
};

const routes = (status: "active" | "completed" | "paused") =>
  vi.spyOn(signingRouteApi, "list").mockResolvedValue({
    items: [
      makeSigningRouteSummary({
        id: ROUTE,
        status,
        profile: { id: "topic", name: { ru: "Тема" } },
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
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  </I18nextProvider>
);

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  serverBoot();
  // Документа нет в списке: имя берётся из файла пакета.
  vi.spyOn(documentApi, "list").mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("пакет: документ изменён после отправки на подпись", () => {
  it("до сборки предупреждает по плану точки и ведёт к карточке маршрута", async () => {
    const getPlan = vi.spyOn(signatureApi, "getPlan").mockResolvedValue({
      profile_id: "topic",
      total: 0,
      signed: 0,
      crypto_total: 0,
      crypto_signed: 0,
      waiting_for_me: 0,
      optional_pending: 0,
      docs: [
        docPlan("annotation", { pinned, working_differs: true }),
        // Версия на подписи без изменений и обычный документ молчат.
        docPlan("review", { pinned }),
        docPlan("report"),
      ],
      route: null,
    });
    routes("active");
    render(
      <PackVersionPreflight
        project={{ id: PROJECT, my_role: "owner" }}
        lang="ru"
        profileId="topic"
        author="ivanov"
      />,
      { wrapper },
    );
    const row = await screen.findByTestId("pack-version-note-annotation");
    expect(getPlan).toHaveBeenCalledWith(PROJECT, {
      profileId: "topic",
      author: "ivanov",
    });
    expect(row.textContent).toMatch(
      /^Документ «annotation» изменён после отправки на подпись: в пакет попадёт версия на подписи от 10\.11, \d\d:32/,
    );
    expect(screen.queryByTestId("pack-version-note-review")).toBeNull();
    expect(screen.queryByTestId("pack-version-note-report")).toBeNull();
    expect(
      await screen.findByTestId("pack-version-send-annotation"),
    ).toHaveAttribute("href", "/projects/p1/submit/cp/topic#signing-route");
  });

  it("после сборки: предупреждение ответа и «Отправить новую версию» управляющему", async () => {
    const list = routes("completed");
    render(
      <PackVersionWarnings
        project={{ id: PROJECT, my_role: "editor" }}
        lang="ru"
        warnings={[warning]}
      />,
      { wrapper },
    );
    expect(screen.getByTestId("pack-version-warnings")).toHaveTextContent(
      "Пакет собран с предупреждениями",
    );
    expect(
      screen.getByTestId("pack-version-note-annotation").textContent,
    ).toMatch(
      /^Документ «Аннотация» изменён после отправки на подпись: в пакет попала версия на подписи от 10\.11/,
    );
    expect(
      await screen.findByTestId("pack-version-send-annotation"),
    ).toHaveTextContent("Отправить новую версию");
    expect(list).toHaveBeenCalledWith(PROJECT, null, expect.anything());
  });

  it("остановленный маршрут: ссылки нет, карточка и так зовёт отправить снова", async () => {
    const list = routes("paused");
    render(
      <PackVersionWarnings
        project={{ id: PROJECT, my_role: "owner" }}
        lang="ru"
        warnings={[warning]}
      />,
      { wrapper },
    );
    await waitFor(() => {
      expect(list).toHaveBeenCalled();
    });
    expect(screen.getByTestId("pack-version-note-annotation")).toBeVisible();
    expect(screen.queryByTestId("pack-version-send-annotation")).toBeNull();
  });

  it("читатель видит предупреждение, но маршрутов не спрашивает", async () => {
    const list = routes("active");
    render(
      <PackVersionWarnings
        project={{ id: PROJECT, my_role: "reader" }}
        lang="ru"
        warnings={[warning]}
      />,
      { wrapper },
    );
    await screen.findByTestId("pack-version-note-annotation");
    expect(screen.queryByTestId("pack-version-send-annotation")).toBeNull();
    expect(list).not.toHaveBeenCalled();
  });

  it("без предупреждений ничего не показывает, чужой код показывает текст сервера", () => {
    const { rerender } = render(
      <PackVersionWarnings
        project={{ id: PROJECT, my_role: "owner" }}
        lang="ru"
        warnings={[]}
      />,
      { wrapper },
    );
    expect(screen.queryByTestId("pack-version-warnings")).toBeNull();
    rerender(
      <PackVersionWarnings
        project={{ id: PROJECT, my_role: "owner" }}
        lang="ru"
        warnings={[
          PackWarningSchema.parse({
            code: "something_new",
            message: "Новое предупреждение",
          }),
        ]}
      />,
    );
    expect(screen.getByTestId("pack-version-warnings")).toHaveTextContent(
      "Новое предупреждение",
    );
  });
});

describe("схема предупреждения пакета", () => {
  it("принимает ответ R14 и ответ без полей сверх контракта W7", () => {
    expect(warning.pinned?.route_id).toBe(ROUTE);
    expect(warning.file).toBe("Аннотация.pdf");
    const bare = PackWarningSchema.parse({
      code: "changed_after_sent",
      doc_id: "annotation",
      sent_at: "2026-11-10T11:32:00Z",
    });
    expect(bare).toMatchObject({ pinned: null, file: null, message: "" });
  });
});
