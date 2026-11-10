import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { projectApi } from "@entities/project";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signatureApi } from "@entities/signature";
import { i18n } from "@shared/lib";
import { SignedVersionPanel } from "./SignedVersionPanel";

const PROJECT = "p1";
const DOC = "topic_application";
const ROUTE = "sr_1";
const SHA = "abcdef0123456789".repeat(4);

type Plan = Awaited<ReturnType<typeof signatureApi.getPlan>>;
type PlanRoute = NonNullable<Plan["route"]>;

const planOf = (
  doc: Partial<Plan["docs"][number]> = {},
  route: Partial<PlanRoute> | null = null,
): Plan => ({
  profile_id: null,
  total: 0,
  signed: 0,
  crypto_total: 0,
  crypto_signed: 0,
  waiting_for_me: 0,
  docs: [
    {
      doc_id: DOC,
      built: true,
      frozen: null,
      slots: [],
      held_by_route: false,
      pinned: {
        sha256: SHA,
        pinned_at: "2026-11-10T11:32:00Z",
        route_id: ROUTE,
        round: 1,
      },
      working_differs: false,
      ...doc,
    },
  ],
  route:
    route === null
      ? null
      : {
          id: ROUTE,
          profile_id: "topic",
          status: "active",
          phase: "approval",
          round: 1,
          current_step: 1,
          steps_total: 2,
          stop_reason: null,
          changed_docs: [],
          ...route,
        },
});

const boot = (mode: "server" | "local") => {
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
    ...LOCAL_BOOTSTRAP,
    mode,
    user:
      mode === "local"
        ? null
        : {
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

const role = (my_role: string | null) => {
  vi.spyOn(projectApi, "get").mockResolvedValue({
    id: PROJECT,
    my_role,
  } as unknown as Awaited<ReturnType<typeof projectApi.get>>);
};

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>
  );
  return render(<SignedVersionPanel projectId={PROJECT} docId={DOC} />, {
    wrapper,
  });
};

beforeEach(async () => {
  await i18n.changeLanguage("ru");
  boot("server");
  role("owner");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("версия на подписи на вкладке «Подписи»", () => {
  it("без версии на подписи панели нет", async () => {
    const getPlan = vi
      .spyOn(signatureApi, "getPlan")
      .mockResolvedValue(planOf({ pinned: null }));
    mount();
    await waitFor(() => {
      expect(getPlan).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("signed-version")).toBeNull();
  });

  it("идущий маршрут: что подписывают, расхождение и почему нельзя снять", async () => {
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(
      planOf({ working_differs: true, held_by_route: true }, {}),
    );
    mount();
    const title = await screen.findByTestId("signed-version-title");
    expect(title.textContent).toMatch(
      /^Подписывается версия от 10\.11, \d\d:32$/,
    );
    expect(screen.getByTestId("signed-version")).toHaveTextContent(
      `SHA-256 ${SHA.slice(0, 12)}`,
    );
    expect(screen.getByTestId("signed-version-differs")).toHaveTextContent(
      "Есть изменения после отправки на подпись.",
    );
    expect(screen.getByTestId("signed-version-open")).toHaveAttribute(
      "href",
      expect.stringMatching(
        new RegExp(`/api/v1/projects/${PROJECT}/docs/${DOC}/pdf/signed$`),
      ),
    );
    const unpin = screen.getByTestId("signed-version-unpin");
    expect(unpin).toBeDisabled();
    const held = screen.getByTestId("signed-version-held");
    expect(held).toHaveTextContent(
      "Пока документ в маршруте подписания, текущую сборку подписать нельзя.",
    );
    expect(unpin).toHaveAttribute("aria-describedby", held.id);
    expect(
      screen.getByRole("link", { name: /Открыть карточку/ }),
    ).toHaveAttribute("href", "/projects/p1/submit/cp/topic#signing-route");
  });

  it("завершённый маршрут: «Подписана версия» и снять с контроля", async () => {
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(
      planOf({}, { status: "completed" }),
    );
    mount();
    expect(
      (await screen.findByTestId("signed-version-title")).textContent,
    ).toMatch(/^Подписана версия от 10\.11/);
    expect(screen.queryByTestId("signed-version-differs")).toBeNull();
    expect(screen.getByTestId("signed-version-unpin")).toBeDisabled();
    expect(screen.getByTestId("signed-version-held")).toHaveTextContent(
      "снимите маршрут с контроля",
    );
  });

  it("маршрут снят с контроля: подтверждение и «Подписывать текущую сборку»", async () => {
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(planOf());
    const unpin = vi
      .spyOn(signatureApi, "unpinVersion")
      .mockResolvedValue(undefined);
    mount();
    expect(
      (await screen.findByTestId("signed-version-title")).textContent,
    ).toMatch(/^Версия на подписи от 10\.11/);
    expect(screen.queryByTestId("signed-version-held")).toBeNull();
    fireEvent.click(screen.getByTestId("signed-version-unpin"));
    expect(
      await screen.findByText(
        /Подписи, поставленные на версию от 10\.11, \d\d:32, перестанут подходить к документу\./,
      ),
    ).toBeInTheDocument();
    expect(unpin).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("signed-version-unpin-confirm"));
    await waitFor(() => {
      expect(unpin).toHaveBeenCalledWith(PROJECT, DOC);
    });
  });

  it("читатель видит версию, но снять её не может", async () => {
    role("reader");
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(planOf());
    mount();
    await screen.findByTestId("signed-version");
    await waitFor(() => {
      expect(screen.queryByTestId("signed-version-unpin")).toBeNull();
    });
    expect(screen.getByTestId("signed-version-open")).toBeInTheDocument();
  });

  it("локальная Студия: маршрут на сервере и предупреждение при снятии", async () => {
    boot("local");
    role(null);
    vi.spyOn(signatureApi, "getPlan").mockResolvedValue(planOf());
    mount();
    await waitFor(() => {
      expect(screen.getByTestId("signed-version-title").textContent).toMatch(
        /\(маршрут на сервере\)$/,
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("signed-version-unpin")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("signed-version-unpin"));
    expect(
      await screen.findByText(
        /Если маршрут на сервере ещё идёт, он остановится\./,
      ),
    ).toBeInTheDocument();
  });
});
