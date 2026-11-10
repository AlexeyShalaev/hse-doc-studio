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
});

describe("SignSubmissionDialog", () => {
  it("документ на подписании по маршруту: причина и ссылка на страницу подписи", async () => {
    const reason = "Документ на подписании по маршруту";
    api.previewSignSubmission.mockResolvedValue({
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
    });
    renderDialog();
    const link = await screen.findByTestId("sign-submission-route-application");
    expect(link).toHaveAttribute("href", "/sign/p1/sr_1");
    expect(link).toHaveTextContent("Открыть страницу подписи");
    expect(screen.getAllByText(reason).length).toBeGreaterThan(0);
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
