import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { gitRemoteApi } from "@entities/git-remote";
import type { GitTlsCertificate } from "@entities/git-sync";
import { renderWithClient } from "../testing/renderConnect";
import { TlsTrustDialog, type TlsTrustMode } from "./TlsTrustDialog";

const CERT: GitTlsCertificate = {
  fingerprint_sha256: "SHA256:b1Kq0vU7m4Zl9Xc2Tn8RjHf3eWyAo5DsPi6GgLxEu0w",
  subject: "CN=gitlab.hse.local",
  issuer: "CN=HSE Internal CA",
  not_before: "2026-01-10T00:00:00Z",
  not_after: "2027-01-10T00:00:00Z",
  self_signed: false,
};

const PEM = "-----BEGIN CERTIFICATE-----\nMIIBdemo\n-----END CERTIFICATE-----";

const setup = () => {
  const update = vi
    .spyOn(gitRemoteApi, "updateHostSettings")
    .mockResolvedValue({
      host: "gitlab.hse.local",
      port: null,
      provider_override: null,
      provider_info: { id: "gitlab", detected_by: "host", version: null },
      ca_present: true,
      pinned_fingerprint: null,
    });
  const onTrusted = vi.fn();
  const onClose = vi.fn();
  const mount = (
    certificate: GitTlsCertificate | null = CERT,
    mode: TlsTrustMode = "untrusted",
    port: number | null = null,
  ) =>
    renderWithClient(
      <TlsTrustDialog
        isOpen
        mode={mode}
        host="gitlab.hse.local"
        port={port}
        certificate={certificate}
        onTrusted={onTrusted}
        onClose={onClose}
      />,
    );
  return { update, onTrusted, onClose, mount };
};

describe("TlsTrustDialog", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("сертификат организации: по умолчанию предлагает добавить CA, проверку не отключает", async () => {
    const { mount } = setup();
    mount();
    expect(
      await screen.findByRole("dialog", {
        name: /Сертификат gitlab.hse.local не из известного центра/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tls-ca")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Добавить сертификат центра (CA)",
        pressed: true,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Отключить проверку сертификата нельзя/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/отключить проверку$/i)).toBeNull();
    expect(screen.getByTestId("tls-submit")).toBeDisabled();
  });

  it("вставленный сертификат уходит на сервер вместе с хостом и портом", async () => {
    const { mount, update, onTrusted } = setup();
    mount(CERT, "untrusted", 8443);
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("tls-ca-text"));
    await user.paste(PEM);
    await user.click(screen.getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: 8443,
        ca_pem: PEM,
      });
    });
    await waitFor(() => {
      expect(onTrusted).toHaveBeenCalled();
    });
  });

  it("файл сертификата читается и попадает в поле", async () => {
    const { mount } = setup();
    mount();
    const user = userEvent.setup();
    const input = await screen.findByTestId("tls-ca-file");
    await user.upload(input, new File([PEM], "hse-ca.crt"));
    await waitFor(() => {
      expect(screen.getByTestId("tls-ca-text")).toHaveValue(PEM);
    });
    expect(screen.getByText(/Из файла hse-ca.crt/)).toBeInTheDocument();
    expect(screen.getByTestId("tls-submit")).toBeEnabled();
  });

  it("закрытый ключ отсекается сразу и не отправляется", async () => {
    const { mount, update } = setup();
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("tls-ca-text"));
    await user.paste(
      "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
    );
    expect(await screen.findByText(/Это закрытый ключ/)).toBeInTheDocument();
    expect(screen.getByTestId("tls-submit")).toBeDisabled();
    expect(update).not.toHaveBeenCalled();
  });

  it("текст без сертификата объясняется после ухода из поля", async () => {
    const { mount } = setup();
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("tls-ca-text"));
    await user.paste("просто текст");
    expect(screen.queryByText(/Не похоже на сертификат/)).toBeNull();
    await user.tab();
    expect(
      await screen.findByText(/Не похоже на сертификат/),
    ).toBeInTheDocument();
  });

  it("закрепление: показывает сертификат и отпечаток, ждёт отметки о сверке", async () => {
    const { mount, update, onTrusted } = setup();
    mount();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: "Закрепить сертификат сервера",
      }),
    );
    const facts = screen.getByTestId("tls-certificate");
    expect(facts).toHaveTextContent("CN=gitlab.hse.local");
    expect(facts).toHaveTextContent("CN=HSE Internal CA");
    expect(
      screen.getByDisplayValue(CERT.fingerprint_sha256),
    ).toBeInTheDocument();
    const submit = screen.getByTestId("tls-submit");
    expect(submit).toBeDisabled();
    await user.click(screen.getByTestId("tls-pin-confirm"));
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => {
      expect(update).toHaveBeenCalledWith({
        host: "gitlab.hse.local",
        port: null,
        pinned_fingerprint: CERT.fingerprint_sha256,
      });
    });
    await waitFor(() => {
      expect(onTrusted).toHaveBeenCalled();
    });
  });

  it("самоподписанный сертификат: сразу предлагает закрепить и помечает его", async () => {
    const { mount } = setup();
    mount({ ...CERT, issuer: CERT.subject, self_signed: true });
    expect(await screen.findByTestId("tls-pin")).toBeInTheDocument();
    expect(screen.getByTestId("tls-certificate")).toHaveTextContent(
      "самоподписанный",
    );
  });

  it("без сертификата закрепить нельзя, объяснено почему", async () => {
    const { mount } = setup();
    mount(null);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: "Закрепить сертификат сервера",
      }),
    );
    expect(
      screen.getByText(/Сервер не прислал сертификат/),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tls-submit")).toBeDisabled();
  });

  it("сертификат изменился: красное предупреждение и ввод имени сервера", async () => {
    const { mount, update } = setup();
    mount(CERT, "pin_mismatch");
    const user = userEvent.setup();
    expect(
      await screen.findByTestId("tls-dialog-pin_mismatch"),
    ).toHaveTextContent("Если администратор не продлевал");
    expect(screen.getByTestId("tls-pin")).toBeInTheDocument();
    await user.click(screen.getByTestId("tls-pin-confirm"));
    expect(screen.getByTestId("tls-submit")).toBeDisabled();
    await user.type(
      screen.getByLabelText(/введи имя сервера/),
      "gitlab.hse.local",
    );
    expect(screen.getByTestId("tls-submit")).toBeEnabled();
    expect(screen.getByTestId("tls-submit")).toHaveTextContent(
      "Закрепить новый сертификат",
    );
    await user.click(screen.getByTestId("tls-submit"));
    await waitFor(() => {
      expect(update).toHaveBeenCalled();
    });
  });

  it("отказ сервера показан в окне, окно остаётся открытым", async () => {
    const { mount, update, onTrusted } = setup();
    update.mockRejectedValue(
      new ApiError("Плохой сертификат", "git_error", 422),
    );
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("tls-ca-text"));
    await user.paste(PEM);
    await user.click(screen.getByTestId("tls-submit"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Git вернул ошибку",
    );
    expect(onTrusted).not.toHaveBeenCalled();
  });

  it("английский язык", async () => {
    await i18n.changeLanguage("en");
    const { mount } = setup();
    mount();
    expect(
      await screen.findByRole("dialog", {
        name: /certificate of gitlab.hse.local is not from a known authority/,
      }),
    ).toBeInTheDocument();
  });
});
