import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { i18n } from "@shared/lib";
import { installViewport } from "@shared/lib/viewport/testing";
import { RUNNER_DISK_STATES, type RunnerDiskStateId } from "../testing";
import { RunnerDiskPanel, type RunnerDiskPanelProps } from "./RunnerDiskPanel";
import { runnerDiskGalleryEntries } from "./runnerDiskGallery";

// Панель «Диск» на эталонах состояний (docs/design/storage-cleanup.md, 4.1).

const handlers = () => ({
  onRefresh: vi.fn(),
  onClean: vi.fn(),
  onCancel: vi.fn(),
});

const renderPanel = (
  state: RunnerDiskStateId,
  props: Partial<RunnerDiskPanelProps> = {},
) => {
  const on = handlers();
  render(
    <RunnerDiskPanel
      view={RUNNER_DISK_STATES[state]}
      runnerName="build-01"
      runnerVersion="0.21.4"
      {...on}
      {...props}
    />,
  );
  return on;
};

const button = (name: RegExp | string) => screen.getByRole("button", { name });

describe("RunnerDiskPanel", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("Docker-раннер: итог, том данных, все блоки и «Очистить всё»", () => {
    renderPanel("docker");
    expect(screen.getByTestId("runner-disk-total")).toHaveTextContent(
      /^Занято 31\.54 GB, можно освободить 17\.42 GB$/,
    );
    expect(screen.getByTestId("runner-disk-volume")).toHaveTextContent(
      "Том данных раннера: свободно",
    );
    for (const id of [
      "old",
      "unused",
      "build-cache",
      "dangling",
      "stopped",
      "cache",
      "volumes",
    ]) {
      expect(screen.getByTestId(`runner-disk-${id}`)).toBeInTheDocument();
    }
    // Кэш раннера на полосе своими категориями.
    expect(screen.getByTestId("disk-usage-legend")).toHaveTextContent(
      "Кэш файлов раннера",
    );
    expect(screen.getByTestId("runner-disk-clean-all")).toBeEnabled();
    expect(screen.queryByTestId("runner-disk-job")).toBeNull();
  });

  it("«Очистить всё» перечисляет цели с размерами и шлёт все цели без отката", async () => {
    const user = userEvent.setup();
    const on = renderPanel("docker");
    await user.click(screen.getByTestId("runner-disk-clean-all"));
    const confirm = screen.getByTestId("runner-disk-confirm");
    expect(
      within(confirm).getByRole("heading", {
        name: "Очистить ненужное на раннере «build-01»?",
      }),
    ).toBeInTheDocument();
    expect(confirm).toHaveTextContent("texlive/texlive:TL2024-historic");
    expect(confirm).toHaveTextContent("Освободится около 17.42 GB");
    expect(screen.queryByTestId("runner-disk-rollback")).toBeNull();
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    expect(on.onClean).toHaveBeenCalledWith({
      targets: [
        "old_versions",
        "unused_images",
        "build_cache",
        "dangling_images",
        "stopped_containers",
        "runner_cache",
      ],
      include_rollback: false,
    });
    expect(screen.queryByTestId("runner-disk-confirm")).toBeNull();
  });

  it("старые версии: флажок отката добавляет предыдущую версию в список и в запрос", async () => {
    const user = userEvent.setup();
    const on = renderPanel("docker");
    await user.click(screen.getByTestId("runner-disk-old-action"));
    const confirm = screen.getByTestId("runner-disk-confirm");
    expect(confirm).not.toHaveTextContent("hse-doc-studio:0.21.4 ");
    expect(confirm).toHaveTextContent("Освободится около 2.18 GB");
    await user.click(screen.getByTestId("runner-disk-rollback"));
    expect(confirm).toHaveTextContent("Освободится около 3.28 GB");
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    expect(on.onClean).toHaveBeenCalledWith({
      targets: ["old_versions"],
      include_rollback: true,
    });
  });

  it("«Отмена» в подтверждении возвращает блоки и ничего не шлёт", async () => {
    const user = userEvent.setup();
    const on = renderPanel("docker");
    await user.click(screen.getByTestId("runner-disk-dangling-action"));
    expect(
      screen.getByRole("heading", { name: "Удалить висячие образы?" }),
    ).toBeInTheDocument();
    await user.click(button("Отмена"));
    expect(screen.getByTestId("runner-disk-dangling")).toBeInTheDocument();
    expect(on.onClean).not.toHaveBeenCalled();
  });

  it("личный раннер у админа: плашка владельца, флажка отката нет", async () => {
    const user = userEvent.setup();
    const on = renderPanel("personal_admin");
    expect(
      screen.getByText(/Это личный раннер, владелец: Мария Келлер/),
    ).toBeVisible();
    expect(screen.getByTestId("runner-disk-old")).toHaveTextContent(
      "Предыдущую версию личного раннера может удалить только владелец.",
    );
    await user.click(screen.getByTestId("runner-disk-old-action"));
    expect(screen.queryByTestId("runner-disk-rollback")).toBeNull();
    expect(screen.getByTestId("runner-disk-confirm")).toHaveTextContent(
      "Владелец раннера получит уведомление об очистке.",
    );
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    expect(on.onClean).toHaveBeenCalledWith({
      targets: ["old_versions"],
      include_rollback: false,
    });
  });

  it("свой личный раннер: флажок отката есть, плашки владельца нет", async () => {
    const user = userEvent.setup();
    renderPanel("personal_owner");
    expect(screen.queryByText(/Это личный раннер/)).toBeNull();
    await user.click(screen.getByTestId("runner-disk-old-action"));
    expect(screen.getByTestId("runner-disk-rollback")).toBeInTheDocument();
  });

  it("идёт очистка: шаг n из total, кнопки выключены, остановка после шага", async () => {
    const user = userEvent.setup();
    const on = renderPanel("running");
    expect(screen.getByTestId("runner-disk-job-title")).toHaveTextContent(
      "Идёт очистка: шаг 3 из 9, освобождено 1.13 GB",
    );
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByTestId("runner-disk-old-action")).toBeDisabled();
    expect(screen.getByTestId("runner-disk-refresh")).toBeDisabled();
    expect(screen.queryByTestId("runner-disk-clean-all")).toBeNull();
    await user.click(screen.getByTestId("runner-disk-cancel"));
    expect(on.onCancel).toHaveBeenCalledWith(
      RUNNER_DISK_STATES.running.command?.id,
    );
  });

  it("остановка уже идёт: кнопка остановки выключена", () => {
    renderPanel("cancelling");
    expect(screen.getByTestId("runner-disk-cancel")).toBeDisabled();
  });

  it("ждём раннер: команду можно отменить до того, как её заберут", () => {
    renderPanel("waiting");
    expect(screen.getByTestId("runner-disk-job")).toHaveAttribute(
      "data-phase",
      "waiting",
    );
    expect(screen.getByTestId("runner-disk-cancel")).toHaveTextContent(
      "Отменить",
    );
  });

  it.each([
    ["done", "done", /^Освобождено 17\.\d\d GB$/],
    ["done_nothing", "nothing", /^Освобождать было нечего$/],
    ["done_error", "error", /^Очистка завершилась с ошибками\. Освобождено/],
    [
      "cancelled",
      "cancelled",
      /^Очистка остановлена\. Освобождено 2\.\d\d GB\.$/,
    ],
    ["expired", "expired", /не забрал команду за 10 минут/],
    ["lost", "lost", /пропал во время очистки/],
  ] as const)("итог %s", (state, phase, title) => {
    renderPanel(state);
    expect(screen.getByTestId("runner-disk-job")).toHaveAttribute(
      "data-phase",
      phase,
    );
    expect(screen.getByTestId("runner-disk-job-title")).toHaveTextContent(
      title,
    );
    expect(screen.queryByTestId("runner-disk-cancel")).toBeNull();
  });

  it("итог с ошибками показывает причину шага", () => {
    renderPanel("done_error");
    expect(screen.getByTestId("runner-disk-job")).toHaveTextContent(
      "a prune operation is already running",
    );
  });

  it("итог скрывается крестиком", async () => {
    const user = userEvent.setup();
    renderPanel("done");
    await user.click(button("Скрыть итог"));
    expect(screen.queryByTestId("runner-disk-job")).toBeNull();
  });

  it("раннер не на связи: плашка, «Обновить» и очистка выключены", () => {
    renderPanel("offline");
    expect(screen.getByText(/Раннер не на связи с/)).toBeVisible();
    expect(screen.getByTestId("runner-disk-refresh")).toBeDisabled();
    expect(screen.getByTestId("runner-disk-clean-all")).toBeDisabled();
    expect(screen.getByTestId("runner-disk-cache-action")).toBeDisabled();
  });

  it("замера нет: подсказка и «Обновить»", async () => {
    const user = userEvent.setup();
    const on = renderPanel("no_report");
    expect(screen.getByTestId("runner-disk-no-report")).toHaveTextContent(
      "Раннер ещё не прислал замер.",
    );
    await user.click(screen.getByTestId("runner-disk-refresh"));
    expect(on.onRefresh).toHaveBeenCalledOnce();
  });

  it("идёт замер: «Обновить» выключена", () => {
    renderPanel("measuring");
    expect(screen.getByTestId("runner-disk-measuring")).toBeVisible();
    expect(screen.getByTestId("runner-disk-refresh")).toBeDisabled();
  });

  it("замер старше суток помечен", () => {
    renderPanel("stale");
    expect(screen.getByTestId("runner-disk-stale")).toHaveTextContent(
      "Замер устарел",
    );
  });

  it("нечего освобождать: кнопки блоков и «Очистить всё» выключены", () => {
    renderPanel("nothing_to_clean");
    expect(screen.getByTestId("runner-disk-old-action")).toBeDisabled();
    expect(screen.getByTestId("runner-disk-dangling-action")).toBeDisabled();
  });

  it("Docker недоступен: Docker-блоков нет, кэш раннера чистится", () => {
    renderPanel("docker_unavailable");
    expect(
      screen.getByText(
        "Раннер не достучался до Docker: образы посчитать нельзя.",
      ),
    ).toBeVisible();
    expect(screen.queryByTestId("runner-disk-old")).toBeNull();
    expect(screen.getByTestId("runner-disk-cache-action")).toBeEnabled();
  });

  it("Kubernetes: плашка про узлы и только кэш раннера", async () => {
    const user = userEvent.setup();
    const on = renderPanel("kubernetes");
    expect(screen.getByText("Образы на узлах чистит Kubernetes")).toBeVisible();
    expect(screen.queryByTestId("runner-disk-old")).toBeNull();
    expect(screen.queryByTestId("runner-disk-volumes")).toBeNull();
    await user.click(screen.getByTestId("runner-disk-clean-all"));
    await user.click(screen.getByTestId("runner-disk-confirm-action"));
    expect(on.onClean).toHaveBeenCalledWith({
      targets: ["runner_cache"],
      include_rollback: false,
    });
  });

  it("локальная Студия: ссылка на Настройки вместо Docker", () => {
    renderPanel("desktop");
    expect(screen.getByText(/Настройки, раздел «Диск»/)).toBeVisible();
    expect(screen.queryByTestId("runner-disk-old")).toBeNull();
  });

  it("старая версия: заглушка с версиями, «Обновить раннер» только у установленного из админки", async () => {
    const user = userEvent.setup();
    const onUpgrade = vi.fn();
    renderPanel("outdated", { onUpgrade });
    const stub = screen.getByTestId("runner-disk-outdated");
    expect(stub).toHaveTextContent("Обновите раннер, чтобы видеть диск");
    expect(stub).toHaveTextContent("Раннер версии 0.21.4");
    expect(stub).toHaveTextContent("Нужна версия 0.22.0 или новее.");
    await user.click(screen.getByTestId("runner-disk-upgrade"));
    expect(onUpgrade).toHaveBeenCalledOnce();
    cleanup();
    renderPanel("outdated");
    expect(screen.queryByTestId("runner-disk-upgrade")).toBeNull();
  });

  it("отказ сервера виден над блоками", () => {
    renderPanel("docker", { error: "Раннер не на связи." });
    expect(screen.getByRole("alert")).toHaveTextContent("Раннер не на связи.");
  });

  it("на телефоне блоки не вылезают за ширину", () => {
    const viewport = installViewport(390);
    renderPanel("docker");
    expect(screen.getByTestId("runner-disk")).toHaveStyle({ minWidth: "0" });
    viewport.restore();
  });
});

describe("галерея «Раннеры: диск»", () => {
  afterEach(cleanup);

  it("есть каждое состояние 4.1 и подтверждения", () => {
    const ids = runnerDiskGalleryEntries().map((e) => e.id);
    for (const state of Object.keys(RUNNER_DISK_STATES)) {
      expect(ids).toContain(`disk_${state}`);
    }
    expect(ids).toEqual(
      expect.arrayContaining([
        "disk_confirm_all",
        "disk_confirm_old_rollback",
        "disk_outdated_upgrade",
      ]),
    );
  });

  it.each(["ru", "en"])(
    "язык %s: записи рисуются без сырых ключей",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of runnerDiskGalleryEntries()) {
        const { container, unmount } = render(<>{entry.render()}</>);
        expect(container.textContent).not.toMatch(
          /(?<!\s)\b(job|old|unused|cache|dangling|stopped|runnerCache|volumes|confirm|outdated|kubernetes|desktop|category|failure)\.[a-z]+[A-Za-z.]*/,
        );
        unmount();
      }
      await i18n.changeLanguage("ru");
    },
  );
});
