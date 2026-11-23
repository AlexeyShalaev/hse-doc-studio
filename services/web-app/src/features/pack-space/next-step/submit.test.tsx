import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { packStudioApi, type PackWorkspace } from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { GALLERY_WORKSPACE } from "../galleryKit";
import { proposeOf, releaseOf, versionStateOf } from "./fixtures";
import {
  FILES,
  SENT,
  gitOf,
  lintOf,
  location,
  mount,
  panel,
  primary,
} from "./nextStepTestKit";

// Раздел отправки внутри панели «Изменения» (S4): заметки, выпуск, отправка, обрыв и повтор.
// Панель грузит отдельный чанк, а автозапись заметок ждёт секунду: тесты не быстрые.
vi.setConfig({ testTimeout: 40_000 });

const ready = async (): Promise<HTMLElement> => {
  const button = await primary();
  await waitFor(
    () => {
      expect(button).toBeEnabled();
    },
    { timeout: 15000 },
  );
  return button;
};

const sentGit = () => gitOf(SENT);

/** Отчёт копии: сделана небольшой правкой, а условия меняют состав документов (нужен minor). */
const softer = () =>
  versionStateOf({
    number_ok: false,
    minimum: "minor",
    changes: { ru: ["Раз"], en: ["One"] },
    reasons: [
      {
        code: "document_scope",
        path: "documents[ts].supported_kinds",
        change: "changed",
        minimum: "minor",
        suggested: "minor",
        hard: true,
        exception: false,
        message: { ru: "Состав документа", en: "Document scope" },
      },
    ],
  });

/** Номер первого вызова: по нему видно, что выпуск шёл раньше отправки. */
const firstCall = (spy: { mock: { invocationCallOrder: number[] } }): number =>
  spy.mock.invocationCallOrder[0] ?? Infinity;

const stubWrite = () => {
  const notes = vi
    .spyOn(packStudioApi, "saveVersionNotes")
    .mockImplementation((_id, _ref, body) => {
      const next = versionStateOf({
        changes: body.changes ?? { ru: [], en: [] },
      });
      vi.spyOn(packStudioApi, "versionState").mockResolvedValue(next);
      return Promise.resolve(next);
    });
  const release = vi
    .spyOn(packStudioApi, "releaseVersion")
    .mockResolvedValue(releaseOf());
  const propose = vi
    .spyOn(packStudioApi, "propose")
    .mockResolvedValue(proposeOf(sentGit()));
  return { notes, release, propose };
};

describe("отправка в панели «Изменения»", () => {
  beforeAll(async () => {
    await Promise.all([
      loadPackSpaceNamespace(),
      loadPackStudioNamespace(),
      loadPackOutcomeNamespace(),
    ]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("всё готово: выпуск, затем отправка одной кнопкой; запрос открылся", async () => {
    const { release, propose } = stubWrite();
    const { spies } = mount();
    const root = await panel();
    const section = await within(root).findByTestId("sp-sb");
    // Галочка «Выпустить версию X» стоит, размер правки и «изменить номер» рядом словами.
    expect(within(section).getByTestId("sp-sb-release-input")).toBeChecked();
    expect(section).toHaveTextContent("Выпустить версию 2026.1.3");
    expect(section).toHaveTextContent("небольшая правка");
    expect(section).toHaveTextContent("изменить номер");
    // Куда уйдёт: человеческими словами, без ветки на первом плане.
    expect(within(section).getByTestId("sp-sb-where")).toHaveTextContent(
      "запрос на слияние, то есть просьба принять ваши правки",
    );
    const button = await ready();
    expect(button).toHaveTextContent("Отправить на рассмотрение");

    spies.git.mockResolvedValue(sentGit());
    await userEvent.click(button);
    await waitFor(() => {
      expect(propose).toHaveBeenCalledTimes(1);
    });
    expect(release).toHaveBeenCalledWith(
      "gallery-ws",
      expect.objectContaining({ version: "2026.1.3" }),
      { kind: "patch", set_default: true },
    );
    expect(propose).toHaveBeenCalledWith(
      "gallery-ws",
      expect.objectContaining({ title: null, description: null }),
    );
    expect(firstCall(release)).toBeLessThan(firstCall(propose));
    // Панель показывает открытый запрос.
    expect(await within(root).findByTestId("sp-ch-open")).toHaveTextContent(
      "#412",
    );
  });

  it("без галочки выпуска версия не выпускается", async () => {
    const { release, propose } = stubWrite();
    mount();
    const section = await screen.findByTestId("sp-sb", undefined, {
      timeout: 15000,
    });
    await userEvent.click(within(section).getByTestId("sp-sb-release-input"));
    await userEvent.click(await ready());
    await waitFor(() => {
      expect(propose).toHaveBeenCalledTimes(1);
    });
    expect(release).not.toHaveBeenCalled();
  });

  it("нет заметок и подсказки нет: кнопка выключена и объясняет почему; написал, записалось само, отправилось", async () => {
    const { notes, release, propose } = stubWrite();
    mount({
      notes: false,
      state: versionStateOf({
        draft_changes: { ru: [], en: [] },
      }),
    });
    const button = await primary();
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Сначала опишите изменения");
    expect(await screen.findByTestId("sp-sb-blocker")).toHaveTextContent(
      "на русском и английском",
    );
    await userEvent.type(
      await screen.findByTestId("sp-sb-notes-ru"),
      "Условия выдачи",
    );
    await userEvent.type(screen.getByTestId("sp-sb-notes-en"), "Terms");
    // Автозапись: сама, без кнопки.
    await waitFor(
      () => {
        expect(notes).toHaveBeenCalledTimes(1);
      },
      { timeout: 8000 },
    );
    expect(notes.mock.calls[0]?.[2]).toEqual({
      changes: { ru: ["Условия выдачи"], en: ["Terms"] },
    });
    await waitFor(() => {
      expect(screen.getByTestId("sp-sb-saved")).toHaveTextContent("Записано");
    });
    await userEvent.click(await ready());
    await waitFor(() => {
      expect(propose).toHaveBeenCalledTimes(1);
    });
    expect(release).toHaveBeenCalledTimes(1);
    // Заметки уже записаны автозаписью: второй раз их не пишут.
    expect(notes).toHaveBeenCalledTimes(1);
  });

  it("нет заметок, а подсказка есть: одна кнопка «Подсказать и отправить» записывает их и отправляет", async () => {
    const { notes, release, propose } = stubWrite();
    mount({ notes: false });
    const button = await ready();
    expect(button).toHaveTextContent("Подсказать и отправить");
    expect(await screen.findByTestId("sp-sb-auto")).toHaveTextContent(
      "Заметки можно не писать",
    );
    expect(screen.queryByTestId("sp-sb-blocker")).toBeNull();

    await userEvent.click(button);
    await waitFor(() => {
      expect(propose).toHaveBeenCalledTimes(1);
    });
    // Подсказка записана в версию до выпуска и отправки.
    expect(notes.mock.calls[0]?.[2]).toEqual({
      changes: {
        ru: [
          "Условия выдачи технического задания: только для проектной работы.",
        ],
        en: ["Statement of Work is now issued for project-type work only."],
      },
    });
    expect(firstCall(notes)).toBeLessThan(firstCall(release));
    expect(firstCall(release)).toBeLessThan(firstCall(propose));
  });

  it("«Подсказать по изменениям» остаётся: заполняет поля, автозапись пишет", async () => {
    const { notes } = stubWrite();
    mount({ notes: false });
    await primary();
    await userEvent.click(await screen.findByTestId("sp-sb-suggest"));
    expect(screen.getByTestId("sp-sb-notes-ru")).toHaveValue(
      "Условия выдачи технического задания: только для проектной работы.",
    );
    await waitFor(
      () => {
        expect(notes).toHaveBeenCalledTimes(1);
      },
      { timeout: 8000 },
    );
  });

  it("пунктов по-русски и по-английски поровну: иначе предупреждение и кнопка выключена", async () => {
    stubWrite();
    mount({ notes: false });
    await primary();
    await userEvent.type(
      await screen.findByTestId("sp-sb-notes-ru"),
      "Раз{Enter}Два",
    );
    await userEvent.type(screen.getByTestId("sp-sb-notes-en"), "One");
    expect(await screen.findByTestId("sp-sb-pairs")).toHaveTextContent(
      "должно быть поровну",
    );
    expect(screen.getByTestId("sp-sb-primary")).toBeDisabled();
  });

  it("ошибки проверки блокируют отправку, кнопка называет их число", async () => {
    mount({
      lint: lintOf([
        {
          severity: "error",
          check: "schema",
          message: "нет поля «name_shrt»",
          path: "hse-cs-sse/templates/coursework/versions/2026.1.3/files/technical_specification/doc.yaml",
          line: 6,
          pointer: null,
        },
      ]),
    });
    const button = await screen.findByRole("button", {
      name: "Исправьте 1 ошибку",
    });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("data-blocker", "errors");
  });

  it.each([
    ["notes", "Записываем заметки к версии"],
    ["release", "Выпускаем версию 2026.1.3"],
    ["send", "Отправляем на рассмотрение"],
  ] as const)(
    "обрыв на шаге «%s»: остановились там, повтор начинается с него",
    async (broken, stepText) => {
      const stubs = stubWrite();
      const failure = new ApiError("упало", "workspace_git_failed", 500);
      const target = {
        notes: stubs.notes,
        release: stubs.release,
        send: stubs.propose,
      }[broken];
      target.mockRejectedValueOnce(failure);
      // Для обрыва на заметках они должны быть написаны человеком, а не записаны заранее.
      const { spies } = mount({ notes: broken !== "notes" });
      spies.git.mockResolvedValue(gitOf());
      if (broken === "notes") {
        await userEvent.click(await screen.findByTestId("sp-sb-suggest"));
        // Автозапись может опередить кнопку: ломаем и её (первый вызов).
      }
      let button = await ready();
      await userEvent.click(button);
      const failed = await screen.findByTestId("sp-sb-failure", undefined, {
        timeout: 15000,
      });
      expect(failed).toHaveTextContent(`Остановились на шаге «${stepText}»`);
      expect(failed).toHaveTextContent("Повтор начнётся с этого шага");
      expect(screen.getByTestId(`sp-sb-step-${broken}`)).toHaveAttribute(
        "data-state",
        "failed",
      );
      const callsBefore = {
        notes: stubs.notes.mock.calls.length,
        release: stubs.release.mock.calls.length,
        propose: stubs.propose.mock.calls.length,
      };
      // Дальше упавшего шага не пошли.
      if (broken === "notes") expect(callsBefore.release).toBe(0);
      if (broken === "release") expect(callsBefore.propose).toBe(0);

      spies.git.mockResolvedValue(sentGit());
      button = await screen.findByRole("button", { name: "Повторить" });
      await waitFor(() => {
        expect(button).toBeEnabled();
      });
      await userEvent.click(button);
      await waitFor(() => {
        expect(stubs.propose).toHaveBeenCalledTimes(broken === "send" ? 2 : 1);
      });
      // Сделанное до обрыва не повторяется.
      if (broken === "release" || broken === "send") {
        expect(stubs.notes.mock.calls.length).toBe(callsBefore.notes);
      }
      expect(stubs.release).toHaveBeenCalledTimes(broken === "release" ? 2 : 1);
    },
  );

  it.each(["credentials_missing", "auth_failed", "push_denied"])(
    "нет доступа к репозиторию (%s): под ошибкой кнопка «Доступ к репозиторию», а не только «Повторить»",
    async (code) => {
      const stubs = stubWrite();
      stubs.propose.mockRejectedValueOnce(
        new ApiError("нет доступа", code, 409),
      );
      mount();
      await userEvent.click(await ready());
      const failed = await screen.findByTestId("sp-sb-failure", undefined, {
        timeout: 15000,
      });
      await userEvent.click(within(failed).getByTestId("sp-sb-access"));
      expect(await screen.findByRole("dialog")).toBeInTheDocument();
    },
  );

  it("сбой без отношения к доступу: кнопки доступа нет", async () => {
    const stubs = stubWrite();
    stubs.propose.mockRejectedValueOnce(
      new ApiError("упало", "workspace_git_failed", 500),
    );
    mount();
    await userEvent.click(await ready());
    const failed = await screen.findByTestId("sp-sb-failure", undefined, {
      timeout: 15000,
    });
    expect(within(failed).queryByTestId("sp-sb-access")).toBeNull();
  });

  it("номер уже выпущен в основной ветке: предлагается перенести правки в свободный", async () => {
    const stubs = stubWrite();
    stubs.release.mockRejectedValueOnce(
      new ApiError("номер занят", "version_taken", 409, {
        suggested: "2026.1.4",
      }),
    );
    const move = vi.spyOn(packStudioApi, "moveVersionEdits").mockResolvedValue({
      version: {
        pack: "hse-cs-sse",
        template: "coursework",
        version: "2026.1.4",
        path: "hse-cs-sse/templates/coursework/versions/2026.1.4",
      },
      previous: "2026.1.3",
      unreleased: false,
      restored: false,
    });
    mount();
    await userEvent.click(await ready());
    const failed = await screen.findByTestId("sp-sb-failure", undefined, {
      timeout: 15000,
    });
    expect(failed).toHaveTextContent(
      "Номер 2026.1.3 уже выпущен в основной ветке",
    );
    await userEvent.click(within(failed).getByTestId("sp-sb-move"));
    await waitFor(() => {
      expect(move).toHaveBeenCalledWith(
        "gallery-ws",
        expect.objectContaining({ version: "2026.1.3" }),
        "2026.1.4",
      );
    });
    expect(stubs.propose).not.toHaveBeenCalled();
  });

  it("не прошла проверка перед отправкой: находки по месту, переход к файлу", async () => {
    const stubs = stubWrite();
    stubs.propose.mockRejectedValueOnce(
      new ApiError("не прошла", "lint_failed", 422, {
        errors: 1,
        warnings: 0,
        findings: [
          {
            severity: "error",
            check: "schema",
            path: "hse-cs-sse/templates/coursework/versions/2026.1.3/files/technical_specification/doc.yaml",
            message: "нет поля name_shrt",
          },
        ],
      }),
    );
    mount();
    await userEvent.click(await ready());
    const list = await screen.findByTestId("sp-sb-findings", undefined, {
      timeout: 15000,
    });
    await userEvent.click(within(list).getByText("нет поля name_shrt"));
    expect(location()).toContain("/content");
    expect(location()).toContain("technical_specification");
  });

  it("нет права писать в репозиторий: форк, указать свою копию и отправить в неё", async () => {
    const stubs = stubWrite();
    stubs.propose.mockRejectedValueOnce(
      new ApiError("нужен форк", "fork_required", 409, { can_create: false }),
    );
    const { spies } = mount();
    await userEvent.click(await ready());
    const fork = await screen.findByTestId("sp-sb-fork", undefined, {
      timeout: 15000,
    });
    expect(fork).toHaveTextContent("В этот репозиторий писать нельзя");
    expect(fork).toHaveTextContent("форк");
    // Пока адрес не указан, кнопка выключена.
    const retry = await screen.findByRole("button", { name: "Повторить" });
    expect(retry).toBeDisabled();
    await userEvent.type(
      within(fork).getByTestId("sp-sb-fork-url"),
      "https://github.com/me/packs.git",
    );
    spies.git.mockResolvedValue(sentGit());
    await waitFor(() => {
      expect(screen.getByTestId("sp-sb-primary")).toBeEnabled();
    });
    await userEvent.click(screen.getByTestId("sp-sb-primary"));
    await waitFor(() => {
      expect(stubs.propose).toHaveBeenCalledTimes(2);
    });
    expect(stubs.propose.mock.calls[1]?.[1]).toMatchObject({
      fork: { url: "https://github.com/me/packs.git" },
    });
    // Выпуск при повторе не делался второй раз.
    expect(stubs.release).toHaveBeenCalledTimes(1);
  });

  it("официальные паки: без согласия с лицензией отправить нельзя", async () => {
    const stubs = stubWrite();
    vi.spyOn(packStudioApi, "official").mockResolvedValue({
      enabled: true,
      repo: {
        url: "https://github.com/AlexeyShalaev/hse-doc-studio.git",
        packs_path: "packs",
        base_branch: "master",
        license: "Apache-2.0",
        license_url: "https://example.test/license",
        contributing_url: "https://example.test/contributing",
      },
    } as never);
    const workspace: PackWorkspace = {
      ...GALLERY_WORKSPACE,
      work_branch: "x",
      official: true,
      license_accepted_at: null,
    };
    mount({ git: gitOf({ workspace }) });
    const license = await screen.findByTestId("sp-sb-license", undefined, {
      timeout: 15000,
    });
    expect(license).toHaveTextContent("Apache-2.0");
    expect(license).toHaveTextContent("от вашего аккаунта");
    await waitFor(() => {
      expect(screen.getByTestId("sp-sb-primary")).toHaveAttribute(
        "data-blocker",
        "consent",
      );
    });
    expect(screen.getByTestId("sp-sb-primary")).toBeDisabled();
    await userEvent.click(within(license).getByTestId("sp-sb-license-accept"));
    await userEvent.click(await ready());
    await waitFor(() => {
      expect(stubs.propose).toHaveBeenCalledTimes(1);
    });
    expect(stubs.propose.mock.calls[0]?.[1]).toMatchObject({
      accept_license: true,
    });
  });

  it("запрос уже открыт, правки новые: «Обновить запрос», без названия и описания", async () => {
    const stubs = stubWrite();
    mount({
      git: gitOf({ ...SENT, dirty: true, head_sha: "bbb" }),
      // Выпуск сделан при первой отправке: версия выпущена.
      state: versionStateOf({
        registered: true,
        changes: { ru: ["Раз"], en: ["One"] },
      }),
    });
    const root = await panel();
    const button = await ready();
    expect(button).toHaveTextContent("Обновить запрос");
    expect(within(root).queryByTestId("sp-sb-request")).not.toBeInTheDocument();
    expect(within(root).getByTestId("sp-sb-where")).toHaveTextContent(
      "уже открытый запрос #412",
    );
    await userEvent.click(button);
    await waitFor(() => {
      expect(stubs.propose).toHaveBeenCalledTimes(1);
    });
    expect(stubs.propose.mock.calls[0]?.[1]).toMatchObject({
      title: null,
      description: null,
    });
  });

  it("«изменить номер»: классы словами, номер меняется, экран идёт за версией", async () => {
    stubWrite();
    const renumber = vi
      .spyOn(packStudioApi, "renumberVersion")
      .mockResolvedValue({
        version: {
          pack: "hse-cs-sse",
          template: "coursework",
          version: "2026.2.0",
          path: "hse-cs-sse/templates/coursework/versions/2026.2.0",
        },
        previous: "2026.1.3",
        unreleased: false,
        restored: false,
      });
    mount();
    await userEvent.click(
      await screen.findByTestId("sp-sb-number", undefined, { timeout: 15000 }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Небольшая правка");
    expect(dialog).toHaveTextContent("Новые возможности");
    expect(dialog).toHaveTextContent("Новая редакция регламента");
    expect(dialog.textContent).not.toMatch(/patch|minor|major/);
    await userEvent.click(within(dialog).getByTestId("sp-number-features"));
    await userEvent.click(within(dialog).getByTestId("sp-number-submit"));
    await waitFor(() => {
      expect(renumber).toHaveBeenCalledWith(
        "gallery-ws",
        expect.objectContaining({ version: "2026.1.3" }),
        "2026.2.0",
      );
    });
  });

  it("правки требуют номера выше: одна фраза с номером вместо ошибки, выпуск включён", async () => {
    mount({ state: softer() });
    const section = await screen.findByTestId("sp-sb", undefined, {
      timeout: 15000,
    });
    expect(within(section).getByTestId("sp-sb-release-input")).toBeEnabled();
    expect(within(section).getByTestId("sp-sb-number-fix")).toHaveTextContent(
      "Эти правки меняют состав документов, номер будет 2026.2.0.",
    );
    expect(section).toHaveTextContent("Выпустить версию 2026.2.0");
    expect(within(section).queryByTestId("sp-sb-number-bad")).toBeNull();
    expect(section.textContent).not.toMatch(/release:|supported_kinds/);
  });

  it("правки требуют номера выше: «Отправить» одним нажатием меняет номер, выпускает и отправляет", async () => {
    const V2 = "hse-cs-sse/templates/coursework/versions/2026.2.0";
    let moved = false;
    const { release, propose } = stubWrite();
    const renumber = vi
      .spyOn(packStudioApi, "renumberVersion")
      .mockImplementation(() => {
        moved = true;
        return Promise.resolve({
          version: {
            pack: "hse-cs-sse",
            template: "coursework",
            version: "2026.2.0",
            path: V2,
          },
          previous: "2026.1.3",
          unreleased: false,
          restored: false,
        });
      });
    mount({
      stateFor: (ref) =>
        ref.version === "2026.2.0"
          ? versionStateOf({
              version: { ...ref, path: V2 },
              changes: { ru: ["Раз"], en: ["One"] },
              by_number: "minor",
              minimum: "minor",
              numbers: {
                patch: "2026.2.1",
                minor: "2026.3.0",
                major: "2027.1.0",
              },
            })
          : softer(),
      gitFor: () =>
        moved
          ? gitOf({
              changed: FILES.map((f) => ({
                ...f,
                path: f.path.replace("2026.1.3", "2026.2.0"),
              })),
            })
          : gitOf(),
    });
    await userEvent.click(await ready());
    await waitFor(
      () => {
        expect(propose).toHaveBeenCalledTimes(1);
      },
      { timeout: 15000 },
    );
    expect(renumber).toHaveBeenCalledWith(
      "gallery-ws",
      expect.objectContaining({ version: "2026.1.3" }),
      "2026.2.0",
    );
    // Выпуск идёт уже по новой версии и по её классу, а не по прежней небольшой правке.
    expect(release).toHaveBeenCalledWith(
      "gallery-ws",
      expect.objectContaining({ version: "2026.2.0" }),
      { kind: "minor", set_default: true },
    );
    expect(firstCall(renumber)).toBeLessThan(firstCall(release));
    expect(firstCall(release)).toBeLessThan(firstCall(propose));
    expect(location()).toContain("/2026.2.0/");
  });

  it("сервер отказал из-за номера: человеческая фраза и «изменить номер», сырой текст свёрнут", async () => {
    stubWrite();
    vi.spyOn(packStudioApi, "propose").mockRejectedValue(
      new ApiError("Проверки пака не прошли", "lint_failed", 422, {
        errors: 1,
        warnings: 0,
        findings: [
          {
            severity: "error",
            check: "lint",
            path: "hse-cs-sse/templates/coursework/versions/2026.1.3",
            message:
              "release: номер 2026.1.3 после 2026.1.2 это patch, а изменения требуют не меньше minor: documents[ts].supported_kinds",
          },
        ],
      }),
    );
    mount();
    await userEvent.click(await ready());
    const failure = await screen.findByTestId("sp-sb-number-failure");
    expect(failure).toHaveTextContent("Номер версии не подходит");
    const box = screen.getByTestId("sp-sb-failure");
    // Сырой текст линтера лежит только внутри «Подробностей».
    const visible = box.cloneNode(true) as HTMLElement;
    visible.querySelectorAll("details").forEach((d) => {
      d.remove();
    });
    expect(visible.textContent).not.toMatch(/release:|supported_kinds/);
    expect(box.querySelector("details")?.textContent).toContain("release:");
    await userEvent.click(screen.getByTestId("sp-sb-fix-number"));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Номер версии");
  });
});
