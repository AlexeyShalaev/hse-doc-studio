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
import { afterEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { projectApi } from "@entities/project";
import { LOCAL_BOOTSTRAP, sessionApi } from "@entities/session";
import { signingRouteApi } from "@entities/signing-route";
import {
  SR_AUTHOR,
  makeRouteParticipant,
  makeSigningRoute,
} from "@entities/signing-route/testing";
import type * as SignatureApiModule from "../../../entities/signature/api/signatureApi";
import type * as IdentityModule from "@entities/signing-identity";
import { SignSubmissionDialog } from "./SignSubmissionDialog";

const api = vi.hoisted(() => ({
  previewSignSubmission: vi.fn(),
  signSubmission: vi.fn(),
}));
// Хуки сущности берут signatureApi из своего модуля, поэтому подменяется он, а не публичный индекс.
vi.mock("../../../entities/signature/api/signatureApi", async (original) => {
  const real = await original<typeof SignatureApiModule>();
  return { ...real, signatureApi: { ...real.signatureApi, ...api } };
});
vi.mock("@entities/signing-identity", async (original) => ({
  ...(await original<typeof IdentityModule>()),
  useSigningIdentities: () => ({
    data: [{ id: "11111111-1111-4111-8111-111111111111", label: "Мой ключ" }],
  }),
}));

const PREVIEW = {
  profile_id: "topic",
  key: {
    id: "11111111-1111-4111-8111-111111111111",
    label: "Мой ключ",
    kind: "self_signed",
    protected: false,
    auto: true,
    signer: "Иван Иванов",
  },
  needs_passphrase: false,
  to_sign: 1,
  docs: [
    {
      doc_id: "application",
      token: "build:abc:def",
      needs_freeze: true,
      can_freeze: true,
      resets: [
        {
          slot_id: "supervisor",
          label: { ru: "Руководитель" },
          signer: "Петров",
          method: "detached",
        },
      ],
      slots: [
        {
          slot_id: "author",
          label: { ru: "Автор" },
          method: "detached",
          status: "stale",
          action: "sign",
          blocker: "",
        },
      ],
      blocker: "",
    },
  ],
};

const renderDialog = (): void => {
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
  render(
    <SignSubmissionDialog
      projectId="p1"
      profileId="topic"
      author={null}
      lang="ru"
      docName={(id) => id}
      onClose={vi.fn()}
    />,
    { wrapper },
  );
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

/** Сервер без почты, вошёл автор маршрута, он же владелец проекта. */
const serveRoute = (route: ReturnType<typeof makeSigningRoute>) => {
  vi.spyOn(sessionApi, "bootstrap").mockResolvedValue({
    ...LOCAL_BOOTSTRAP,
    mode: "server",
    user: {
      id: SR_AUTHOR.id,
      name: SR_AUTHOR.name,
      email: "author@edu.hse.ru",
      avatar_initials: "ИИ",
      is_instance_admin: false,
      email_verified: true,
      locale: null,
      org_roles: [],
    },
  });
  vi.spyOn(projectApi, "get").mockResolvedValue({
    id: "p1",
    my_role: "owner",
  } as unknown as Awaited<ReturnType<typeof projectApi.get>>);
  vi.spyOn(signingRouteApi, "get").mockResolvedValue(route);
};

/** Случай с сервера: автор с ЭП согласовал при отправке, два руководителя не приняли приглашение. */
const earlyApproverRoute = (
  author: Partial<Parameters<typeof makeRouteParticipant>[0]> = {},
) => {
  const invited = (id: string, persona: string, step: string) =>
    makeRouteParticipant({
      id,
      persona,
      user_id: null,
      invitation_id: `inv_${id}`,
      name: `${step}***@hse.ru`,
      card_name: null,
      membership: "invited",
      assignments: [{ doc_id: "application", slot_id: persona }],
      method: "image",
      state: "invited",
      next_action: "wait",
      changes_visible: true,
      approved_at: null,
    });
  return makeSigningRoute({
    id: "sr_1",
    project_id: "p1",
    phase: "approval",
    current_step: 2,
    steps: [
      [
        makeRouteParticipant({
          method: "detached",
          state: "waiting",
          next_action: "wait",
          ...author,
        }),
      ],
      [invited("srp_sup", "supervisor", "h")],
      [invited("srp_acad", "academic_supervisor", "s")],
    ],
  });
};

describe("SignSubmissionDialog", () => {
  const heldPreview = () => {
    const reason = "Документ на подписании по маршруту";
    return {
      ...PREVIEW,
      to_sign: 0,
      docs: [
        {
          ...PREVIEW.docs[0],
          needs_freeze: false,
          resets: [],
          blocker: reason,
          route_id: "sr_1",
          slots: [
            { ...PREVIEW.docs[0]?.slots[0], action: "none", blocker: reason },
          ],
        },
      ],
    };
  };

  it("документ на подписании по маршруту: почему и когда, кого ждём, ссылки приглашённым", async () => {
    api.previewSignSubmission.mockResolvedValue(heldPreview());
    serveRoute(earlyApproverRoute());
    renderDialog();
    expect(
      await screen.findByTestId("route-wait-lead", {}, { timeout: 5000 }),
    ).toHaveTextContent(
      "Вы уже согласовали. Электронную подпись Студия попросит поставить после фиксации PDF, когда согласуют: Научный руководитель h***@hse.ru (шаг 2 из 3, приглашение не принято), Академический руководитель s***@hse.ru (шаг 3 из 3, приглашение не принято).",
    );
    expect(screen.getByTestId("route-wait-now")).toHaveTextContent(
      "Сейчас ждём: Научный руководитель h***@hse.ru, приглашение не принято.",
    );
    expect(screen.getByTestId("route-wait-invited")).toHaveTextContent(
      "Сервер не отправляет письма: скопируйте ссылку и перешлите её сами.",
    );
    expect(screen.getByTestId("route-wait-copy-srp_sup")).toBeEnabled();
    expect(screen.getByTestId("route-wait-copy-srp_acad")).toBeEnabled();
    // Не своя очередь: на страницу подписи не зовём, слот назван подписью по маршруту.
    expect(screen.queryByTestId("route-wait-go")).toBeNull();
    expect(screen.getByText("подпись по маршруту")).toBeInTheDocument();
    expect(
      screen.getByTestId("sign-submission-route-application"),
    ).toHaveTextContent("Документ на подписании по маршруту");
    expect(screen.getByRole("button", { name: /Подписать$/ })).toBeDisabled();
  });

  it("своя очередь по маршруту: сказано и есть переход на страницу подписи", async () => {
    api.previewSignSubmission.mockResolvedValue(heldPreview());
    serveRoute(
      earlyApproverRoute({
        state: "to_approve",
        next_action: "approve",
        approved_at: null,
      }),
    );
    renderDialog();
    expect(
      await screen.findByTestId("route-wait-lead", {}, { timeout: 5000 }),
    ).toHaveTextContent("Сейчас ваша очередь: согласуйте документы.");
    expect(screen.getByTestId("route-wait-go")).toHaveAttribute(
      "href",
      "/sign/p1/sr_1",
    );
  });

  it("asks to confirm the reset and sends the tokens from the preview", async () => {
    api.previewSignSubmission.mockResolvedValue(PREVIEW);
    api.signSubmission.mockResolvedValue({
      frozen_docs: ["application"],
      results: [
        { doc_id: "application", slot_id: "author", ok: true, message: "" },
      ],
      plan: {
        profile_id: "topic",
        total: 2,
        signed: 1,
        crypto_total: 2,
        crypto_signed: 1,
        waiting_for_me: 0,
        docs: [],
      },
    });
    renderDialog();

    const confirm = await screen.findByRole("checkbox");
    const sign = screen.getByRole("button", { name: /Подписать$/ });
    // Повторная фиксация сбросит подпись руководителя: без подтверждения подписать нельзя.
    expect(sign).toBeDisabled();
    fireEvent.click(confirm);
    expect(sign).toBeEnabled();
    fireEvent.click(sign);

    await waitFor(() => {
      expect(api.signSubmission).toHaveBeenCalledWith("p1", {
        profile_id: "topic",
        author: null,
        identity_id: PREVIEW.key.id,
        passphrase: "",
        confirm_reset: true,
        expected: { application: "build:abc:def" },
      });
    });
    expect(await screen.findByText(/Подписано 1 из 2/)).toBeInTheDocument();
  });
});
