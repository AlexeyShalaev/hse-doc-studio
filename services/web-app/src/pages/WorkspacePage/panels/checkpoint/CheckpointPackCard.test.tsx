import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps, ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import { signingRouteApi } from "@entities/signing-route";
import { makeSigningRouteSummary } from "@entities/signing-route/testing";
import { submissionApi } from "@entities/submission";
import { systemApi } from "@entities/system";
import { i18n } from "@shared/lib";
import { CheckpointPackCard } from "./CheckpointPackCard";

vi.mock("@entities/template-catalog", () => ({
  useVersionDetail: () => ({ data: undefined }),
}));
// Предупреждения версии на подписи проверяют свои тесты.
vi.mock("@features/signing-version", () => ({
  PackVersionPreflight: () => null,
  PackVersionWarnings: () => null,
}));

type Props = ComponentProps<typeof CheckpointPackCard>;
type Plan = Awaited<ReturnType<typeof signatureApi.getPlan>>;

const PROJECT = {
  id: "p1",
  folder: "/projects/kp",
  lang: "ru",
  my_role: "owner",
  meta: {},
  supervisor: { name: "Петров П. П." },
  lock: {
    pack_id: "hse-cs-sse",
    template_id: "coursework",
    version: "2026.1.3",
  },
} as unknown as Props["project"];

const plan = (signed: number, total: number): Plan => ({
  profile_id: "topic",
  total,
  signed,
  crypto_total: 0,
  crypto_signed: 0,
  waiting_for_me: 0,
  optional_pending: 0,
  docs: [],
  route: null,
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

const renderCard = () =>
  render(
    <CheckpointPackCard
      project={PROJECT}
      profileId="topic"
      packedItems={[{ doc_id: "topic_application", signatures: ["author"] }]}
      isTeam={false}
      authors={[]}
      selectedAuthorSlug={null}
      onSelectAuthor={() => undefined}
    />,
    { wrapper },
  );

beforeEach(async () => {
  await i18n.changeLanguage("ru");
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
  vi.spyOn(systemApi, "getArchiveFormats").mockResolvedValue({
    formats: [{ id: "zip", label: "ZIP", available: true }],
  } as Awaited<ReturnType<typeof systemApi.getArchiveFormats>>);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("карточка «Папка проекта»: пакет при маршруте подписания", () => {
  it("маршрут не завершён: пункт готовности вместо ошибки после нажатия, кнопка выключена", async () => {
    vi.spyOn(signingRouteApi, "list").mockResolvedValue({
      items: [
        makeSigningRouteSummary({
          status: "active",
          phase: "approval",
          current_step: 3,
          steps_total: 3,
          waiting_for: [
            { name: "Сидоров С. С.", persona: "academic_supervisor" },
          ],
        }),
      ],
    });
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(2, 3));
    const preflight = vi.spyOn(submissionApi, "preflightCustomFiles");
    const create = vi.spyOn(submissionApi, "create");

    renderCard();

    const text =
      "Маршрут подписания не завершён (шаг 3 из 3). Сейчас ждём: Академический руководитель Сидоров С. С.";
    const row = await screen.findByTestId("pack-gate-route");
    expect(row).toHaveTextContent(text);
    expect(row).toHaveAttribute("data-tone", "err");
    expect(
      screen.getByRole("link", { name: "Открыть карточку «Подписание»" }),
    ).toHaveAttribute("href", "/projects/p1/submit/cp/topic#signing-route");
    const button = screen.getByTestId("pack-submit");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", text);

    await userEvent.click(button);
    expect(preflight).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it("все обязательные подписи готовы: кнопка доступна, пакет собирается", async () => {
    vi.spyOn(signingRouteApi, "list").mockResolvedValue({
      items: [makeSigningRouteSummary({ status: "completed" })],
    });
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(plan(3, 3));
    const preflight = vi
      .spyOn(submissionApi, "preflightCustomFiles")
      .mockResolvedValue([]);
    const create = vi
      .spyOn(submissionApi, "create")
      .mockResolvedValue({ warnings: [] } as unknown as Awaited<
        ReturnType<typeof submissionApi.create>
      >);

    renderCard();

    const button = screen.getByTestId("pack-submit");
    await waitFor(() => {
      expect(signatureApi.getPlan).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    expect(screen.queryByTestId("pack-gate-route")).toBeNull();
    expect(screen.queryByTestId("pack-gate-signatures")).toBeNull();

    await userEvent.click(button);
    await waitFor(() => {
      expect(create).toHaveBeenCalled();
    });
    expect(preflight).toHaveBeenCalled();
  });
});
