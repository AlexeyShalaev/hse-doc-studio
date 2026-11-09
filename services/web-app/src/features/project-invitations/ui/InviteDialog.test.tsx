import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  projectInvitationsApi,
  type ProjectInvitationCreated,
} from "@entities/invitation";
import { projectApi } from "@entities/project";
import { i18n } from "@shared/lib/i18n";
import { invitationText } from "../lib/invitationText";
import { InviteDialog } from "./InviteDialog";

const PROJECT = "p_01";
const DRAFT =
  "Здравствуйте, Хади Мухаммед!\n\nПриглашаю вас в проект «КП» в HSE Doc Studio в роли научного руководителя.\n\nС уважением,\nАлексей Шалаев, группа МСПИН261";
const DRAFT_EMAIL =
  "Здравствуйте, Пётр Иванов!\n\nПриглашаю вас в проект «КП» в HSE Doc Studio в роли соавтора.";
const LINK = "https://studio.example.org/project-invite/hspi_x";

const created = (
  delivery: ProjectInvitationCreated["delivery"],
  link: string | null,
): ProjectInvitationCreated => ({
  invitation: {
    id: "inv_1",
    invitee: {
      kind: "email",
      user_id: null,
      name: null,
      email_hint: "hadi@hse.ru",
    },
    role: "reviewer",
    persona: "supervisor",
    can_share: false,
    show_sources: true,
    can_edit_all: false,
    message: null,
    invited_by: null,
    created_at: "2026-11-08T10:00:00Z",
    expires_at: "2026-11-15T10:00:00Z",
    status: "pending",
    sent_count: 1,
    last_sent_at: "2026-11-08T10:00:00Z",
  },
  delivery,
  link,
});

const mount = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <InviteDialog
        projectId={PROJECT}
        isOpen
        onClose={onClose}
        preset={{ role: "reviewer", persona: "supervisor" }}
      />
    </QueryClientProvider>,
  );
  return { onClose };
};

const field = () => screen.getByTestId<HTMLTextAreaElement>("invite-message");

describe("InviteDialog: готовый текст приглашения", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    vi.spyOn(projectApi, "get").mockResolvedValue({ authors: [] } as never);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("подставляет текст, составленный сервером по роли и персоне", async () => {
    const draft = vi
      .spyOn(projectInvitationsApi, "draft")
      .mockResolvedValue({ message: DRAFT });
    mount();

    await waitFor(() => {
      expect(field().value).toBe(DRAFT);
    });
    expect(draft).toHaveBeenCalledWith(
      PROJECT,
      { user_id: null, email: null, role: "reviewer", persona: "supervisor" },
      expect.anything(),
    );
    expect(screen.getByTestId("invite-message-hint")).toBeInTheDocument();
    expect(screen.queryByTestId("invite-message-reset")).toBeNull();
  });

  it("пересобирает текст, когда введена почта, пока его не правили", async () => {
    const user = userEvent.setup();
    const draft = vi
      .spyOn(projectInvitationsApi, "draft")
      .mockImplementation((_id, body) =>
        Promise.resolve({ message: body.email ? DRAFT_EMAIL : DRAFT }),
      );
    mount();
    await waitFor(() => {
      expect(field().value).toBe(DRAFT);
    });

    await user.type(screen.getByTestId("invite-email"), "petr@hse.ru");

    await waitFor(() => {
      expect(field().value).toBe(DRAFT_EMAIL);
    });
    expect(draft).toHaveBeenLastCalledWith(
      PROJECT,
      expect.objectContaining({ email: "petr@hse.ru" }),
      expect.anything(),
    );
  });

  it("правку можно отменить кнопкой «Вернуть исходный текст»", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectInvitationsApi, "draft").mockResolvedValue({
      message: DRAFT,
    });
    mount();
    await waitFor(() => {
      expect(field().value).toBe(DRAFT);
    });

    await user.clear(field());
    await user.type(field(), "Свой текст");
    expect(field().value).toBe("Свой текст");
    await user.click(screen.getByTestId("invite-message-reset"));

    expect(field().value).toBe(DRAFT);
    expect(screen.queryByTestId("invite-message-reset")).toBeNull();
  });

  it("отправляет отредактированный текст", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectInvitationsApi, "draft").mockResolvedValue({
      message: DRAFT,
    });
    const create = vi
      .spyOn(projectInvitationsApi, "create")
      .mockResolvedValue(created("email", null));
    const { onClose } = mount();
    await waitFor(() => {
      expect(field().value).toBe(DRAFT);
    });

    await user.type(screen.getByTestId("invite-email"), "hadi@hse.ru");
    await user.type(field(), "\nЖду ваших замечаний.");
    await user.click(screen.getByTestId("invite-submit"));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
    expect(create).toHaveBeenCalledWith(
      PROJECT,
      expect.objectContaining({
        email: "hadi@hse.ru",
        persona: "supervisor",
        message: `${DRAFT}\nЖду ваших замечаний.`,
      }),
    );
  });

  it("без почты на сервере даёт скопировать приглашение: текст и ссылку", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectInvitationsApi, "draft").mockResolvedValue({
      message: DRAFT,
    });
    vi.spyOn(projectInvitationsApi, "create").mockResolvedValue(
      created("manual", LINK),
    );
    mount();
    await waitFor(() => {
      expect(field().value).toBe(DRAFT);
    });
    await user.type(screen.getByTestId("invite-email"), "hadi@hse.ru");
    await user.click(screen.getByTestId("invite-submit"));

    const message = await screen.findByTestId("invite-manual-message");
    expect(message.textContent).toBe(DRAFT);
    await user.click(screen.getByTestId("invite-copy"));

    expect(await navigator.clipboard.readText()).toBe(`${DRAFT}\n\n${LINK}`);
  });

  it("без готового текста поле пустое и письмо уходит без сообщения", async () => {
    const user = userEvent.setup();
    vi.spyOn(projectInvitationsApi, "draft").mockRejectedValue(
      new Error("offline"),
    );
    const create = vi
      .spyOn(projectInvitationsApi, "create")
      .mockResolvedValue(created("email", null));
    mount();

    await user.type(screen.getByTestId("invite-email"), "hadi@hse.ru");
    expect(field().value).toBe("");
    expect(screen.queryByTestId("invite-message-hint")).toBeNull();
    await user.click(screen.getByTestId("invite-submit"));

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith(
        PROJECT,
        expect.objectContaining({ message: null }),
      );
    });
  });

  it("invitationText: без сообщения только ссылка", () => {
    expect(invitationText(null, LINK)).toBe(LINK);
    expect(invitationText("Текст", LINK)).toBe(`Текст\n\n${LINK}`);
  });
});
