import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@shared/api";
import { REVEAL_FINGERPRINT, gitRemoteApi } from "@entities/git-remote";
import {
  renderWithClient,
  resetConnectEnvironment,
} from "../testing/renderConnect";
import { HostKeyDialog, type HostKeyDialogProps } from "./HostKeyDialog";

const KEYS = [
  { type: "ssh-rsa", fingerprint_sha256: "SHA256:rsaRsaRsa" },
  { type: "ssh-ed25519", fingerprint_sha256: "SHA256:edEdEd" },
];

const mount = (props: Partial<HostKeyDialogProps> = {}) => {
  const onTrusted = vi.fn();
  const onClose = vi.fn();
  renderWithClient(
    <HostKeyDialog
      isOpen
      mode="unknown"
      host="git.hse.ru"
      port={null}
      keys={KEYS}
      onTrusted={onTrusted}
      onClose={onClose}
      {...props}
    />,
  );
  return { onTrusted, onClose };
};

describe("HostKeyDialog: незнакомый сервер", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("показывает отпечатки, по умолчанию в фокусе «Отмена»", () => {
    mount();
    const dialog = screen.getByRole("dialog", {
      name: /Сервер git.hse.ru подключается впервые/,
    });
    expect(
      within(dialog).getByLabelText("Отпечаток ключа ssh-ed25519"),
    ).toHaveValue("SHA256:edEdEd");
    expect(
      within(dialog).getByLabelText("Отпечаток ключа ssh-rsa"),
    ).toHaveValue("SHA256:rsaRsaRsa");
    expect(screen.getByRole("button", { name: "Отмена" })).toHaveFocus();
  });

  it("доверять можно только после паузы в три секунды", async () => {
    const trust = vi.spyOn(gitRemoteApi, "trustHost").mockResolvedValue();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { onTrusted } = mount();
    const button = screen.getByRole("button", { name: /Доверять серверу/ });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("(3)");

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("(1)");

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent(/^Доверять серверу$/);

    await user.click(button);
    await waitFor(() => {
      expect(trust).toHaveBeenCalledWith({
        host: "git.hse.ru",
        port: null,
        // из набора ключей подтверждаем ed25519
        fingerprint_sha256: "SHA256:edEdEd",
      });
    });
    expect(onTrusted).toHaveBeenCalledTimes(1);
  });

  it("«Отмена» ничего не доверяет", async () => {
    const trust = vi.spyOn(gitRemoteApi, "trustHost").mockResolvedValue();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { onClose, onTrusted } = mount();
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(trust).not.toHaveBeenCalled();
    expect(onTrusted).not.toHaveBeenCalled();
  });

  it("известные серверы: на странице провайдера есть ссылка на отпечатки", () => {
    mount({ host: "github.com" });
    expect(
      screen.getByRole("link", { name: /Отпечатки ключей github.com/ }),
    ).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("сбой записи показан в окне и не закрывает его", async () => {
    vi.spyOn(gitRemoteApi, "trustHost").mockRejectedValue(
      new ApiError("Нет прав на файл", "git_error", 500),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { onTrusted } = mount();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    await user.click(screen.getByRole("button", { name: /Доверять серверу/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Git вернул ошибку",
    );
    expect(onTrusted).not.toHaveBeenCalled();
  });

  it("если сервер уже известен с другим ключом, окно переходит к замене", async () => {
    vi.spyOn(gitRemoteApi, "trustHost").mockRejectedValue(
      new ApiError("Ключ изменился", "host_key_changed", 409, {
        expected: "SHA256:OLD",
        actual: "SHA256:edEdEd",
      }),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mount();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    await user.click(screen.getByRole("button", { name: /Доверять серверу/ }));
    expect(
      await screen.findByRole("dialog", {
        name: /Ключ сервера git.hse.ru изменился/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/Отпечаток ключа/, {
        selector: "input[value='SHA256:OLD']",
      }),
    ).toBeInTheDocument();
  });
});

describe("HostKeyDialog: ключ сервера изменился", () => {
  beforeEach(async () => {
    await resetConnectEnvironment();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("красное предупреждение, прежний и новый отпечатки рядом", () => {
    mount({
      mode: "changed",
      knownFingerprints: ["SHA256:OLD"],
      keys: [KEYS[1] ?? { type: "", fingerprint_sha256: "" }],
    });
    const dialog = screen.getByRole("dialog", {
      name: /Ключ сервера git.hse.ru изменился/,
    });
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "Это может быть подменой сервера",
    );
    expect(within(dialog).getByText("Был")).toBeInTheDocument();
    expect(within(dialog).getByText("Стал")).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("SHA256:OLD")).toBeInTheDocument();
    expect(
      within(dialog).getByDisplayValue("SHA256:edEdEd"),
    ).toBeInTheDocument();
    // Доверия «одним щелчком» здесь нет.
    expect(
      within(dialog).queryByRole("button", { name: /Доверять/ }),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Отмена" })).toHaveFocus();
  });

  it("заменить ключ можно только набрав имя сервера", async () => {
    const trust = vi.spyOn(gitRemoteApi, "trustHost").mockResolvedValue();
    const user = userEvent.setup();
    const { onTrusted } = mount({
      mode: "changed",
      knownFingerprints: ["SHA256:OLD"],
      keys: [KEYS[1] ?? { type: "", fingerprint_sha256: "" }],
    });
    const replace = screen.getByRole("button", { name: "Заменить ключ" });
    expect(replace).toBeDisabled();
    await user.type(screen.getByLabelText(/введи имя сервера/), "git.hse");
    expect(replace).toBeDisabled();
    await user.type(screen.getByLabelText(/введи имя сервера/), ".ru");
    expect(replace).toBeEnabled();
    await user.click(replace);
    await waitFor(() => {
      expect(trust).toHaveBeenCalledWith({
        host: "git.hse.ru",
        port: null,
        fingerprint_sha256: "SHA256:edEdEd",
        replace: true,
        confirm_host: "git.hse.ru",
      });
    });
    expect(onTrusted).toHaveBeenCalledTimes(1);
  });

  describe("проверка не принесла ключей", () => {
    it("сначала узнаёт новый отпечаток, а заменить ключ можно только после этого", async () => {
      const trust = vi
        .spyOn(gitRemoteApi, "trustHost")
        .mockRejectedValueOnce(
          new ApiError("Ключ изменился", "host_key_changed", 409, {
            expected: "SHA256:OLD",
            actual: "SHA256:NEW",
          }),
        )
        .mockResolvedValue();
      const user = userEvent.setup();
      const { onTrusted } = mount({ mode: "changed", keys: [] });
      // Пока отпечатка нет, показываем ожидание и не даём заменить.
      expect(
        screen.getByText("Получаем отпечаток нового ключа…"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Заменить ключ" }),
      ).toBeDisabled();
      await waitFor(() => {
        expect(trust).toHaveBeenCalledWith({
          host: "git.hse.ru",
          port: null,
          fingerprint_sha256: REVEAL_FINGERPRINT,
        });
      });
      expect(await screen.findByDisplayValue("SHA256:NEW")).toBeInTheDocument();
      expect(screen.getByDisplayValue("SHA256:OLD")).toBeInTheDocument();
      await user.type(screen.getByLabelText(/введи имя сервера/), "git.hse.ru");
      await user.click(screen.getByRole("button", { name: "Заменить ключ" }));
      await waitFor(() => {
        expect(trust).toHaveBeenLastCalledWith({
          host: "git.hse.ru",
          port: null,
          fingerprint_sha256: "SHA256:NEW",
          replace: true,
          confirm_host: "git.hse.ru",
        });
      });
      expect(onTrusted).toHaveBeenCalledTimes(1);
      // После замены отпечаток второй раз не запрашивается.
      expect(trust).toHaveBeenCalledTimes(2);
    });

    it("не удалось узнать отпечаток: ошибка и «Повторить», заменить нельзя", async () => {
      const trust = vi
        .spyOn(gitRemoteApi, "trustHost")
        .mockRejectedValueOnce(new ApiError("Нет сети", "offline", 502))
        .mockRejectedValueOnce(
          new ApiError("Ключ изменился", "host_key_changed", 409, {
            expected: "SHA256:OLD",
            actual: "SHA256:NEW",
          }),
        );
      const user = userEvent.setup();
      mount({ mode: "changed", keys: [] });
      const retry = await screen.findByRole("button", { name: "Повторить" });
      await user.type(screen.getByLabelText(/введи имя сервера/), "git.hse.ru");
      expect(
        screen.getByRole("button", { name: "Заменить ключ" }),
      ).toBeDisabled();
      await user.click(retry);
      expect(await screen.findByDisplayValue("SHA256:NEW")).toBeInTheDocument();
      expect(trust).toHaveBeenCalledTimes(2);
      expect(
        screen.getByRole("button", { name: "Заменить ключ" }),
      ).toBeEnabled();
    });
  });
});
