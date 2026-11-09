import { readFileSync } from "node:fs";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import type { MyRunner } from "@entities/runner";
import { MyRunnersView, type MyRunnersViewProps } from "./ui/MyRunnersView";
import { ConnectRunnerDialog } from "./ui/ConnectRunnerDialog";

const NOW = Date.parse("2026-10-30T10:00:00Z");
const RUNNER: MyRunner = {
  id: "r1",
  name: "MacBook Анны",
  state: "online",
  host_kind: "desktop",
  tags: ["ai", "tex"],
  concurrency: 1,
  ai_concurrency: 2,
  version: "0.1.0",
  created_at: "2026-10-28T10:00:00Z",
  last_seen_at: "2026-10-30T09:59:50Z",
  last_seen_ip: "203.0.113.7",
  paused: false,
  paused_by: null,
  revoked: false,
  running_jobs: 1,
  ai_endpoints: [{ name: "ollama", flavor: "ollama" }],
  features: [],
};

const noop = () => undefined;
const renderView = (extra: Partial<MyRunnersViewProps> = {}) =>
  render(
    <MemoryRouter>
      <MyRunnersView
        status="ready"
        runners={[RUNNER]}
        tokens={[]}
        enabled
        serverVersion="0.3.0"
        now={NOW}
        onConnect={noop}
        onRename={noop}
        onTogglePause={noop}
        onRotate={noop}
        onReconnect={noop}
        onRevoke={noop}
        onRevokeToken={noop}
        {...extra}
      />
    </MemoryRouter>,
  );

describe("«Мои раннеры»: вид", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("строка раннера: состояние, вид, устаревшая версия, ИИ-адреса, нагрузка", () => {
    renderView();
    const row = screen.getByTestId("my-runner-row-r1");
    expect(row).toHaveTextContent("Студия на компьютере");
    expect(row).toHaveTextContent("ollama");
    expect(screen.getByTestId("my-runner-outdated-r1")).toHaveTextContent(
      "Устарел",
    );
    expect(screen.getByTestId("my-runner-status-r1")).toHaveAttribute(
      "data-status",
      "online",
    );
    expect(screen.getByText("Идёт 1 сборка")).toBeInTheDocument();
    expect(screen.getByText("IP 203.0.113.7")).toBeInTheDocument();
    expect(screen.getByText("до 1 сборки · до 2 ИИ")).toBeInTheDocument();
  });

  it("пусто: пояснение раскрыто, кнопка подключения ведёт к диалогу", async () => {
    const onConnect = vi.fn();
    renderView({ runners: [], onConnect });
    expect(screen.getByTestId("my-runners-empty")).toBeInTheDocument();
    expect(screen.getByTestId("my-runners-how")).toHaveAttribute("open");
    await userEvent.click(screen.getByTestId("my-runners-empty-connect"));
    expect(onConnect).toHaveBeenCalledOnce();
  });

  it("отозванные свёрнуты под кнопкой", async () => {
    renderView({
      runners: [
        RUNNER,
        {
          ...RUNNER,
          id: "r2",
          name: "Старый",
          state: "revoked",
          revoked: true,
        },
      ],
    });
    expect(screen.queryByTestId("my-runner-row-r2")).toBeNull();
    await userEvent.click(screen.getByTestId("my-runners-show-revoked"));
    expect(screen.getByTestId("my-runner-row-r2")).toBeInTheDocument();
  });

  it("выключены администратором: баннер, подключение недоступно", () => {
    renderView({ enabled: false, runners: [{ ...RUNNER, state: "disabled" }] });
    expect(screen.getByTestId("my-runners-disabled")).toHaveTextContent(
      "Администратор выключил личные раннеры.",
    );
    expect(screen.getByTestId("my-runner-connect")).toBeDisabled();
    expect(screen.getByTestId("my-runner-status-r1")).toHaveAttribute(
      "data-status",
      "disabled",
    );
    // Баннер уже сказал, где идут сборки; нагрузка выключенного раннера не показывается.
    expect(screen.queryByText("Сборки идут на общих раннерах.")).toBeNull();
    expect(screen.queryByText("Идёт 1 сборка")).toBeNull();
  });

  it("на паузе и не в сети: «Не берёт сборки», а не «Свободен»", () => {
    renderView({
      runners: [
        { ...RUNNER, state: "paused", paused: true, running_jobs: 0 },
        { ...RUNNER, id: "r2", state: "offline", running_jobs: 0 },
      ],
    });
    expect(screen.getAllByText("Не берёт сборки")).toHaveLength(2);
    expect(screen.queryByText("Свободен")).toBeNull();
  });

  it("меньше минуты назад: «в сети только что»", () => {
    renderView({
      runners: [{ ...RUNNER, state: "paused", paused: true }],
    });
    expect(
      screen.getByText(/в сети только что, IP 203\.0\.113\.7/),
    ).toBeInTheDocument();
  });

  it("пауза администратора: пояснение, снять её хозяин не может", async () => {
    const onTogglePause = vi.fn();
    renderView({
      onTogglePause,
      runners: [
        { ...RUNNER, state: "paused", paused: true, paused_by: "admin" },
      ],
    });
    expect(screen.getByTestId("my-runner-status-r1")).toHaveAttribute(
      "data-paused-by",
      "admin",
    );
    expect(screen.getByText(/Приостановил администратор/)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("my-runner-actions-r1"));
    const resume = await screen.findByTestId("my-runner-pause-r1");
    expect(resume).toHaveAttribute("aria-disabled", "true");
  });

  it("ошибка загрузки с повтором", async () => {
    const onRetry = vi.fn();
    renderView({ status: "error", onRetry });
    await userEvent.click(
      within(screen.getByTestId("my-runners-error")).getByRole("button"),
    );
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("у Студии вместо смены токена «Подключить заново»", async () => {
    const onReconnect = vi.fn();
    renderView({ onReconnect });
    await userEvent.click(screen.getByTestId("my-runner-actions-r1"));
    expect(screen.queryByTestId("my-runner-rotate-r1")).toBeNull();
    await userEvent.click(await screen.findByTestId("my-runner-reconnect-r1"));
    expect(onReconnect).toHaveBeenCalledWith(RUNNER);
  });
});

// «Мои раннеры» открываются в окне настроек: его затемнение .settings-modal-overlay лежит
// поверх страницы. Меню «⋯» и подсказки уходят порталом в body и должны быть выше него,
// иначе на десктопе меню открывается под окном и кнопка будто не нажимается.
const SETTINGS_OVERLAY_LAYER = (() => {
  const css = readFileSync("src/index.css", "utf8");
  const start = css.indexOf(".settings-modal-overlay {");
  const rule = css.slice(start, css.indexOf("}", start));
  const z = /z-index:\s*(\d+)/.exec(rule);
  if (start < 0 || z === null) throw new Error("нет слоя окна настроек");
  return Number(z[1]);
})();

const layerOf = (el: HTMLElement): number => {
  const wrapper = el.closest<HTMLElement>(
    "[data-radix-popper-content-wrapper]",
  );
  const z = Number.parseInt(getComputedStyle(wrapper ?? el).zIndex, 10);
  return Number.isNaN(z) ? 0 : z;
};

describe("«Мои раннеры»: меню «⋯» в окне настроек", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  const RUNNERS: MyRunner[] = [
    { ...RUNNER, id: "online", running_jobs: 0 },
    { ...RUNNER, id: "busy", running_jobs: 2, concurrency: 2 },
    {
      ...RUNNER,
      id: "paused",
      state: "paused",
      paused: true,
      paused_by: "owner",
      running_jobs: 2,
    },
  ];

  it.each([
    ["десктоп", 1360],
    ["телефон", 390],
  ])(
    "%s: меню открывается в любом состоянии раннера, пункт срабатывает",
    async (_, width) => {
      const viewport = installViewport(width);
      try {
        const onRename = vi.fn();
        renderView({ runners: RUNNERS, onRename });
        for (const runner of RUNNERS) {
          await userEvent.click(
            screen.getByTestId(`my-runner-actions-${runner.id}`),
          );
          const rename = await screen.findByTestId(
            `my-runner-rename-${runner.id}`,
          );
          const menu = rename.closest<HTMLElement>(".adm-menu");
          if (menu === null) throw new Error("меню не открылось");
          expect(menu).toHaveAttribute(
            "data-form",
            width < 768 ? "sheet" : "menu",
          );
          if (width >= 768) {
            // На телефоне шторку поднимает index.css (z-index: 120 !important).
            expect(layerOf(menu)).toBeGreaterThan(SETTINGS_OVERLAY_LAYER);
          }
          await userEvent.click(rename);
          expect(onRename).toHaveBeenLastCalledWith(runner);
        }
        expect(onRename).toHaveBeenCalledTimes(RUNNERS.length);
      } finally {
        viewport.restore();
      }
    },
  );

  it("меню неиспользованного токена тоже над окном настроек", async () => {
    const viewport = installViewport(1360);
    try {
      renderView({
        tokens: [
          {
            id: "t1",
            label: "Сервер на даче",
            created_at: "2026-10-30T09:00:00Z",
            expires_at: "2026-10-31T09:00:00Z",
            used: false,
            revoked: false,
          },
        ],
      });
      await userEvent.click(screen.getByTestId("my-runner-token-actions-t1"));
      const revoke = await screen.findByTestId("my-runner-token-revoke-t1");
      expect(layerOf(revoke)).toBeGreaterThan(SETTINGS_OVERLAY_LAYER);
    } finally {
      viewport.restore();
    }
  });

  it("подсказка «Устарел» не прячется под окном настроек", async () => {
    // Radix меряет подсказку через ResizeObserver; в jsdom его нет.
    const noop = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = noop;
        unobserve = noop;
        disconnect = noop;
      },
    );
    try {
      renderView();
      act(() => {
        screen.getByTestId("my-runner-outdated-r1").focus();
      });
      const hints = await screen.findAllByText(
        "Сервер новее (0.3.0): обновите раннер.",
      );
      const hint = hints.find((el) =>
        el.closest("[data-radix-popper-content-wrapper]"),
      );
      if (hint === undefined) throw new Error("подсказка не открылась");
      expect(layerOf(hint)).toBeGreaterThan(SETTINGS_OVERLAY_LAYER);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("«Подключить раннер»: диалог", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("код из Студии проверяется и нормализуется", async () => {
    const onPairCode = vi.fn();
    render(
      <ConnectRunnerDialog
        isOpen
        onClose={noop}
        onPairCode={onPairCode}
        onCreateToken={noop}
      />,
    );
    const input = screen.getByTestId("runner-pair-code-input");
    await userEvent.type(input, "bcd");
    await userEvent.click(screen.getByTestId("runner-pair-code-continue"));
    expect(onPairCode).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Код состоит из восьми букв и цифр/),
    ).toBeInTheDocument();
    await userEvent.type(input, "f2345");
    expect(input).toHaveValue("BCDF-2345");
    await userEvent.click(screen.getByTestId("runner-pair-code-continue"));
    expect(onPairCode).toHaveBeenCalledWith("BCDF-2345");
  });

  it("токен для сервера: метка и срок уходят в запрос", async () => {
    const onCreateToken = vi.fn();
    render(
      <ConnectRunnerDialog
        isOpen
        onClose={noop}
        onPairCode={noop}
        onCreateToken={onCreateToken}
      />,
    );
    await userEvent.click(screen.getByTestId("runner-connect-tab-server"));
    await userEvent.type(
      screen.getByTestId("runner-token-label"),
      " Домашний сервер ",
    );
    await userEvent.click(screen.getByTestId("runner-token-ttl-168"));
    await userEvent.click(screen.getByTestId("runner-token-create-submit"));
    expect(onCreateToken).toHaveBeenCalledWith({
      label: "Домашний сервер",
      ttl_hours: 168,
    });
  });

  it("готовый токен: пример ИИ-адресов копируется, рядом ссылка на документацию", () => {
    render(
      <ConnectRunnerDialog
        isOpen
        onClose={noop}
        onPairCode={noop}
        onCreateToken={noop}
        created={{
          token: {
            id: "t1",
            label: "",
            created_at: "2026-10-30T08:00:00Z",
            expires_at: "2026-10-31T08:00:00Z",
            used: false,
            revoked: false,
          },
          secret: "hsrt_x",
          command: "HSE_RUNNER__TOKEN=hsrt_x hse-doc-studio runner",
          docker_command: "docker run hse",
        }}
      />,
    );
    const example = within(
      screen.getByTestId("runner-token-ai-example"),
    ).getByRole<HTMLInputElement>("textbox");
    expect(example.value).toContain("HSE_RUNNER__AI_ENDPOINTS=");
    expect(screen.getByTestId("runner-token-ai-docs")).toHaveAttribute(
      "href",
      expect.stringContaining("docs/ru/deploy/runners.md"),
    );
  });
});
