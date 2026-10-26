import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { ProfileValidationFailed, profileApi } from "../api/profileApi";
import type { Profile } from "../api/profileSchemas";
import { ProfileForm, type ProfileFormProps } from "./ProfileForm";

const DEFAULT_PROFILE: Profile = {
  name: null,
  email: null,
  effective_name: "HSE Doc Studio",
  effective_email: "studio@hse-doc-studio.local",
  is_default: true,
  commit_preview: "HSE Doc Studio <studio@hse-doc-studio.local>",
};

const CUSTOM_PROFILE: Profile = {
  name: "Алексей Шалаев",
  email: "ashalaev@edu.hse.ru",
  effective_name: "Алексей Шалаев",
  effective_email: "ashalaev@edu.hse.ru",
  is_default: false,
  commit_preview: "Алексей Шалаев <ashalaev@edu.hse.ru>",
};

const renderForm = (props: Partial<ProfileFormProps> = {}) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProfileForm profile={DEFAULT_PROFILE} {...props} />
    </QueryClientProvider>,
  );
};

const nameInput = () => screen.getByLabelText("Имя");
const emailInput = () => screen.getByLabelText("E-mail");
const saveButton = () =>
  screen.getByRole("button", { name: /Сохранить|Сохраняем/ });

describe("ProfileForm", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("empty: amber notice with the shared signature, empty preview, save disabled", () => {
    renderForm();
    expect(
      screen.getByText(/HSE Doc Studio <studio@hse-doc-studio.local>/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("profile-preview")).toHaveTextContent(
      "Имя <e-mail>",
    );
    expect(saveButton()).toBeDisabled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the privacy note and the no-reply hint", () => {
    renderForm();
    expect(screen.getByText(/будут видны всем/)).toBeInTheDocument();
    expect(screen.getByText(/users\.noreply\.github\.com/)).toBeInTheDocument();
  });

  it("builds the commit preview live from normalized values", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(nameInput(), "  Иван   Смирнов ");
    await user.type(emailInput(), "Ivan@EDU.hse.ru");
    expect(screen.getByTestId("profile-preview")).toHaveTextContent(
      "Иван Смирнов <Ivan@edu.hse.ru>",
    );
  });

  it("invalid: a field error appears after blur and the field is marked invalid", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(emailInput(), "not-an-email");
    expect(screen.queryByRole("alert")).toBeNull();
    await user.tab();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Укажи адрес вида name@example.com.",
    );
    expect(emailInput()).toHaveAttribute("aria-invalid", "true");
  });

  it("submitting an invalid form shows every error, focuses the first and sends nothing", async () => {
    const user = userEvent.setup();
    const update = vi.spyOn(profileApi, "update");
    renderForm();
    await user.type(emailInput(), "x");
    await user.click(saveButton());
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(nameInput()).toHaveFocus();
    expect(update).not.toHaveBeenCalled();
  });

  it("valid: sends normalized values, then shows Saved and reports the profile", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    vi.spyOn(profileApi, "update").mockResolvedValue(CUSTOM_PROFILE);
    renderForm({ onSaved });
    await user.type(nameInput(), " Алексей  Шалаев ");
    await user.type(emailInput(), "ashalaev@EDU.hse.ru");
    expect(saveButton()).toBeEnabled();
    await user.click(saveButton());
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(CUSTOM_PROFILE);
    });
    expect(profileApi.update).toHaveBeenCalledWith({
      name: "Алексей Шалаев",
      email: "ashalaev@edu.hse.ru",
    });
    expect(screen.getByText("Сохранено")).toBeInTheDocument();
  });

  it("saving: inputs are read-only and the button is disabled until the request ends", async () => {
    const user = userEvent.setup();
    let finish: (value: Profile) => void = () => undefined;
    vi.spyOn(profileApi, "update").mockReturnValue(
      new Promise<Profile>((resolve) => {
        finish = resolve;
      }),
    );
    renderForm();
    await user.type(nameInput(), "Иван");
    await user.type(emailInput(), "i@b.ru");
    await user.click(saveButton());
    await waitFor(() => {
      expect(screen.getByText("Сохраняем…")).toBeInTheDocument();
    });
    expect(nameInput()).toHaveAttribute("readonly");
    expect(emailInput()).toHaveAttribute("readonly");
    expect(saveButton()).toBeDisabled();
    finish(CUSTOM_PROFILE);
    await waitFor(() => {
      expect(screen.getByText("Сохранено")).toBeInTheDocument();
    });
  });

  it("server 422 marks the field named in loc and clears when the user edits it", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "update").mockRejectedValue(
      new ProfileValidationFailed([
        {
          loc: ["body", "email"],
          code: "email_invalid",
          msg: "серверный текст",
        },
      ]),
    );
    renderForm();
    await user.type(nameInput(), "Иван");
    await user.type(emailInput(), "i@b.ru");
    await user.click(saveButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Укажи адрес вида name@example.com.");
    expect(emailInput()).toHaveAttribute("aria-invalid", "true");
    await user.type(emailInput(), "m");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("server 422 with an unknown code falls back to the server message", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "update").mockRejectedValue(
      new ProfileValidationFailed([
        { loc: ["body", "name"], code: "future_rule", msg: "Правило сервера" },
      ]),
    );
    renderForm();
    await user.type(nameInput(), "Иван");
    await user.type(emailInput(), "i@b.ru");
    await user.click(saveButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Правило сервера",
    );
  });

  it("other failures show an error notice with the server text and can be dismissed", async () => {
    const user = userEvent.setup();
    vi.spyOn(profileApi, "update").mockRejectedValue(
      new ApiError("Диск только для чтения", "unknown_error", 500),
    );
    renderForm();
    await user.type(nameInput(), "Иван");
    await user.type(emailInput(), "i@b.ru");
    await user.click(saveButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Диск только для чтения",
    );
    await user.click(screen.getByRole("button", { name: "Скрыть" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("saved profile: fields are prefilled, no amber notice, save waits for a change", async () => {
    const user = userEvent.setup();
    renderForm({ profile: CUSTOM_PROFILE });
    expect(nameInput()).toHaveValue("Алексей Шалаев");
    expect(emailInput()).toHaveValue("ashalaev@edu.hse.ru");
    expect(screen.queryByText(/общей подписью Студии/)).toBeNull();
    expect(saveButton()).toBeDisabled();
    await user.type(nameInput(), "x");
    expect(saveButton()).toBeEnabled();
  });

  it("allowUnchanged lets the dialog continue without a request", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const update = vi.spyOn(profileApi, "update");
    renderForm({
      profile: CUSTOM_PROFILE,
      allowUnchanged: true,
      onSaved,
      submitLabel: "Продолжить",
    });
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(onSaved).toHaveBeenCalledWith(CUSTOM_PROFILE);
    expect(update).not.toHaveBeenCalled();
  });

  it("renders cancel and the extra action slot", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderForm({
      onCancel,
      actionsStart: <button type="button">Слот</button>,
    });
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onCancel).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Слот" })).toBeInTheDocument();
  });

  it("anchors are put on the field wrappers for the settings search", () => {
    renderForm({ anchors: { name: "profile-name", email: "profile-email" } });
    expect(document.getElementById("profile-name")).toContainElement(
      nameInput(),
    );
    expect(document.getElementById("profile-email")).toContainElement(
      emailInput(),
    );
  });

  it("speaks English when the interface language is English", async () => {
    await i18n.changeLanguage("en");
    const user = userEvent.setup();
    renderForm();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    await user.type(screen.getByLabelText("E-mail"), "x");
    await user.tab();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter an address like name@example.com.",
    );
  });
});
