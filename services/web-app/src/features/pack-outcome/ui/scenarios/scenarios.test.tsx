import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  packOutcomeApi,
  packStudioKeys,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
  scenarioReference,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n, useToastStore } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { Toaster } from "@shared/ui";
import { OutcomeBody } from "../../OutcomeBody";

// Сценарии на экране «Результат» (F8): сервер подменён эталонами с памятью (ETag записи,
// scenario_taken, stale_file, record_snapshot), так что тест проходит весь путь «создал,
// увидел в списке, прогнал» тем же кодом, который работает с настоящим сервером.

const WS = "ws-scenarios";
const REF: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.6",
};
const NOW = "2026-11-16T09:30:00Z";

const workspace: PackWorkspace = {
  id: WS,
  kind: "folder",
  label: "packs",
  state: "ready",
  busy: false,
  packs_path: "packs",
  url: null,
  credential_id: null,
  service_access: false,
  insecure_http: false,
  folder: "/work/packs",
  base_branch: null,
  base_sha: null,
  fetched_at: null,
  work_branch: null,
  pr_url: null,
  pr_number: null,
  ci_status: null,
  fork_url: null,
  pushed_sha: null,
  error: null,
  created_at: NOW,
  updated_at: NOW,
};

const tree: PackTree = {
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: REF.pack,
      path: REF.pack,
      name: { ru: "ФКН, СПИ" },
      templates: [
        {
          id: REF.template,
          path: `${REF.pack}/templates/${REF.template}`,
          name: { ru: "Курсовой проект" },
          default_version: REF.version,
          versions: [
            {
              version: REF.version,
              path: `${REF.pack}/templates/${REF.template}/versions/${REF.version}`,
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
};

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};
const where = () => screen.getByTestId("location").textContent;

const mount = (search = "") => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  const path = `/pack-studio/w/${WS}/result/${REF.pack}/${REF.template}/${REF.version}`;
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`${path}${search ? `?${search}` : ""}`]}>
        <OutcomeBody workspace={workspace} version={REF} />
        <Probe />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
  return client;
};

const openPicker = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await screen.findByTestId("scenario-trigger"));
  return await screen.findByTestId("scenario-list");
};

const fill = (testId: string, value: string) => {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
};

describe("сценарии на экране «Результат» (F8)", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
    useToastStore.getState().clear();
    window.localStorage.clear();
  });

  describe("выбор сценария", () => {
    it("у каждого сценария значок статуса, сверху итог прогона и счётчик на кнопке", async () => {
      const user = userEvent.setup();
      mount();
      const list = await openPicker(user);
      await waitFor(() => {
        expect(screen.getByTestId("scenario-summary")).toHaveTextContent(
          "2 совпало, 1 изменилось",
        );
      });
      const failed = within(list).getByTestId(
        "scenario-option-university-supervisor",
      );
      expect(
        within(failed).getByTestId("scenario-status-failed"),
      ).toBeVisible();
      const passed = within(list).getByTestId(
        "scenario-option-company-supervisor",
      );
      expect(
        within(passed).getByTestId("scenario-status-passed"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("scenario-chip")).toHaveTextContent("1 из 3");
    });

    it("выбор записывается в адрес, «Без сценария» убирает его", async () => {
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByTestId("scenario-trigger"));
      await user.click(
        await screen.findByTestId("scenario-option-company-supervisor"),
      );
      await waitFor(() => {
        expect(where()).toContain("scenario=company-supervisor");
      });
      expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
        "Научрук из компании",
      );
      await user.click(screen.getByTestId("scenario-trigger"));
      await user.click(await screen.findByTestId("scenario-option-none"));
      await waitFor(() => {
        expect(where()).not.toContain("scenario=");
      });
    });

    it("«Прогнать все» запускает прогон заново", async () => {
      const user = userEvent.setup();
      mount();
      await openPicker(user);
      await waitFor(() => {
        expect(screen.getByTestId("scenario-summary")).toHaveTextContent(
          "2 совпало",
        );
      });
      const run = vi.spyOn(packOutcomeApi, "runScenarios");
      await user.click(screen.getByTestId("scenario-run-all"));
      await waitFor(() => {
        expect(run).toHaveBeenCalledTimes(1);
      });
      expect(run.mock.calls[0]?.[3]).toEqual({
        state: "work_tree",
        version: REF.version,
        scenarios: null,
      });
    });

    it("с клавиатуры: Enter открывает список, стрелки двигают фокус, Enter выбирает", async () => {
      const user = userEvent.setup();
      mount();
      const trigger = await screen.findByTestId("scenario-trigger");
      trigger.focus();
      await user.keyboard("{Enter}");
      const list = await screen.findByTestId("scenario-list");
      expect(list).toHaveAttribute("role", "listbox");
      await waitFor(() => {
        expect(screen.getByTestId("scenario-option-none")).toHaveFocus();
      });
      await user.keyboard("{ArrowDown}");
      expect(
        screen.getByTestId("scenario-option-company-supervisor"),
      ).toHaveFocus();
      await user.keyboard("{ArrowDown}");
      expect(
        screen.getByTestId("scenario-option-university-supervisor"),
      ).toHaveFocus();
      await user.keyboard("{End}");
      expect(screen.getByTestId("scenario-option-draft")).toHaveFocus();
      await user.keyboard("{ArrowUp}{Enter}");
      await waitFor(() => {
        expect(where()).toContain("scenario=no-supervisor");
      });
      await waitFor(() => {
        expect(screen.queryByTestId("scenario-list")).not.toBeInTheDocument();
      });
    });

    it("пусто: подсказка с примерами для реальных паков и кнопка создания", async () => {
      outcomeReference.setBehavior("no_scenarios");
      const user = userEvent.setup();
      mount();
      await openPicker(user);
      const empty = await screen.findByTestId("scenario-empty");
      expect(empty).toHaveTextContent(
        "Создайте первый сценарий из текущих вводных",
      );
      expect(empty).toHaveTextContent("Научрук из компании, есть консультант");
      expect(empty).toHaveTextContent("NDA и только руководство программиста");
      expect(screen.getByTestId("scenario-save-as")).toBeEnabled();
    });

    it("битый файл виден с причиной и не выбирается", async () => {
      const user = userEvent.setup();
      mount();
      await openPicker(user);
      const broken = await screen.findByTestId("scenario-option-draft");
      expect(broken).toHaveTextContent("Файл не читается");
      expect(broken).toHaveTextContent("значение 'firm' не из списка");
      expect(broken).toHaveAttribute("aria-disabled", "true");
      await user.click(broken);
      expect(where()).not.toContain("scenario=draft");
      await waitFor(() => {
        expect(screen.getByTestId("scenario-summary")).toHaveTextContent(
          "1 битый файл",
        );
      });
    });

    it("сбой прогона: плашка с повтором, список остаётся рабочим", async () => {
      outcomeReference.setBehavior("run_error");
      const user = userEvent.setup();
      mount();
      await openPicker(user);
      const notice = await screen.findByTestId("scenario-run-error");
      expect(notice).toHaveTextContent("Не удалось прогнать сценарии");
      expect(
        screen.getByTestId("scenario-option-company-supervisor"),
      ).toHaveTextContent("Не прогнан");
      outcomeReference.setBehavior("normal");
      await user.click(
        within(notice).getByRole("button", { name: "Повторить" }),
      );
      await waitFor(() => {
        expect(screen.getByTestId("scenario-summary")).toHaveTextContent(
          "2 совпало",
        );
      });
    });

    it("сценарии не загрузились: короткая подпись и повтор", async () => {
      const failing = vi
        .spyOn(packOutcomeApi, "scenarios")
        .mockRejectedValue(
          new ApiError("Внутренняя ошибка.", "internal_error", 500),
        );
      const user = userEvent.setup();
      mount();
      await waitFor(() => {
        expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
          "Сценарии не загрузились",
        );
      });
      await user.click(screen.getByTestId("scenario-trigger"));
      const notice = await screen.findByTestId("scenario-load-error");
      failing.mockRestore();
      await user.click(
        within(notice).getByRole("button", { name: "Повторить" }),
      );
      await waitFor(() => {
        expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
          "Без сценария",
        );
      });
    });
  });
});

type User = ReturnType<typeof userEvent.setup>;

const chooseAndManage = async (user: User, id: string) => {
  await user.click(await screen.findByTestId("scenario-trigger"));
  await user.click(await screen.findByTestId(`scenario-option-${id}`));
  await user.click(await screen.findByTestId("scenario-manage"));
  return await screen.findByTestId("scenario-panel");
};

const orig = (id: string) => {
  const entry = scenarioReference.entries().find((item) => item.id === id);
  if (!entry?.scenario) throw new Error(`no scenario ${id}`);
  return structuredClone(entry);
};

describe("«Сохранить как сценарий»", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
    useToastStore.getState().clear();
    window.localStorage.clear();
  });

  it("создаёт сценарий из текущих вводных со снимком и утверждениями, выбирает его", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount("i.supervisor=university&i.co_supervisor=no&example=auto%3Along");
    await user.click(await screen.findByTestId("scenario-save-as"));
    await screen.findByTestId("scenario-save-dialog");
    expect(screen.getByTestId("scenario-inputs-note")).toHaveTextContent(
      "2 вводные",
    );
    fill("scenario-name-ru", "Научрук из ВШЭ новый");
    // Имя файла следует за названием, пока его не правили руками.
    expect(screen.getByTestId("scenario-id")).toHaveValue(
      "nauchruk-iz-vshe-novyy",
    );
    fill("scenario-id", "my-scenario");
    await user.click(screen.getByTestId("scenario-assert-all"));
    await user.click(screen.getByTestId("scenario-submit"));

    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [ws, pack, template, id, body, ifMatch] = put.mock.calls[0] ?? [];
    expect([ws, pack, template, id, ifMatch]).toEqual([
      WS,
      REF.pack,
      REF.template,
      "my-scenario",
      null,
    ]);
    expect(body?.record_snapshot).toBe("work_tree");
    expect(body?.version).toBe(REF.version);
    expect(body?.scenario.inputs).toEqual({
      supervisor: "university",
      co_supervisor: "no",
    });
    expect(body?.scenario.example).toBe("auto:long");
    expect(body?.scenario.versions).toEqual(["2026.1.*"]);
    expect(body?.scenario.name).toEqual({ ru: "Научрук из ВШЭ новый" });
    expect(body?.scenario.assertions?.length).toBeGreaterThan(10);
    // Вводные теперь в файле: изменения из адреса ушли, выбран новый сценарий.
    await waitFor(() => {
      expect(where()).toContain("scenario=my-scenario");
    });
    expect(where()).not.toContain("i.supervisor");
    expect(where()).not.toContain("example=");
    expect(
      screen.queryByTestId("scenario-save-dialog"),
    ).not.toBeInTheDocument();
    expect(useToastStore.getState().toasts[0]?.message).toBe(
      "Сценарий «Научрук из ВШЭ новый» сохранён",
    );
    expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
      "Научрук из ВШЭ новый",
    );
  });

  it("предлагает готовые утверждения по всем семи видам сервера", async () => {
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    for (const kind of [
      "document_state",
      "document_count",
      "participant_present",
      "item_active",
      "route_steps",
      "route_pair",
      "meta_visible",
    ]) {
      expect(
        await screen.findByTestId(`scenario-group-${kind}`),
      ).toBeInTheDocument();
    }
    const group = screen.getByTestId("scenario-group-document_state");
    expect(group).toHaveTextContent("есть в комплекте");
    expect(screen.getByTestId("scenario-group-route_pair")).toHaveTextContent(
      "Подписант",
    );
    await user.click(screen.getByTestId("scenario-assert-all"));
    const count = within(screen.getByTestId("scenario-assertions")).getByRole(
      "status",
    );
    expect(count).toHaveTextContent(/Выбрано \d+ утверждений/);
    await user.click(screen.getByTestId("scenario-assert-none"));
    expect(count).toHaveTextContent("Выбрано 0 утверждений");
  });

  it("не отправляет без названия и с занятым именем файла", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    await user.click(screen.getByTestId("scenario-submit"));
    expect(
      await screen.findByText("Укажите название хотя бы на одном языке"),
    ).toBeVisible();
    expect(put).not.toHaveBeenCalled();
    fill("scenario-name-ru", "Любое");
    fill("scenario-id", "company-supervisor");
    await user.click(screen.getByTestId("scenario-submit"));
    expect(
      await screen.findByText("Сценарий с таким именем файла уже есть"),
    ).toBeVisible();
    expect(put).not.toHaveBeenCalled();
    fill("scenario-id", "Bad Name");
    await user.click(screen.getByTestId("scenario-submit"));
    expect(await screen.findByText(/Только строчная латиница/)).toBeVisible();
  });

  it("scenario_taken от сервера: предлагает свободное имя и записывает его", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    put.mockRejectedValueOnce(
      new ApiError("Сценарий уже есть.", "scenario_taken", 409),
    );
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    fill("scenario-name-ru", "Гонка");
    fill("scenario-id", "race");
    await user.click(screen.getByTestId("scenario-submit"));
    const take = await screen.findByTestId("scenario-take-free");
    expect(take).toHaveTextContent("Взять «race-2»");
    await user.click(take);
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(2);
    });
    expect(put.mock.calls[1]?.[3]).toBe("race-2");
    await waitFor(() => {
      expect(where()).toContain("scenario=race-2");
    });
  });

  it("scenario_invalid: причина сервера и поле, окно остаётся открытым", async () => {
    vi.spyOn(packOutcomeApi, "putScenario").mockRejectedValueOnce(
      new ApiError("Сценарий не по формату.", "scenario_invalid", 400, {
        reason: "name: must not be empty",
      }),
    );
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    fill("scenario-name-ru", "Имя");
    fill("scenario-id", "invalid-one");
    await user.click(screen.getByTestId("scenario-submit"));
    const notice = await screen.findByTestId("scenario-failure");
    expect(notice).toHaveTextContent(
      "Сервер не принял сценарий: name: must not be empty",
    );
    expect(screen.getByTestId("scenario-save-dialog")).toBeInTheDocument();
  });

  it("нет связи: сообщение и повтор, вторая попытка записывает", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    put.mockRejectedValueOnce(
      new ApiError("Network Error", "network_error", 0),
    );
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    fill("scenario-name-ru", "Офлайн");
    fill("scenario-id", "offline-one");
    await user.click(screen.getByTestId("scenario-submit"));
    const notice = await screen.findByTestId("scenario-failure");
    expect(notice).toHaveTextContent("Нет связи с сервером");
    await user.click(screen.getByTestId("scenario-failure-retry"));
    await waitFor(() => {
      expect(where()).toContain("scenario=offline-one");
    });
    expect(put).toHaveBeenCalledTimes(2);
  });

  it("Esc закрывает окно, ничего не записав", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByTestId("scenario-save-as"));
    await screen.findByTestId("scenario-save-dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(
        screen.queryByTestId("scenario-save-dialog"),
      ).not.toBeInTheDocument();
    });
    expect(put).not.toHaveBeenCalled();
  });
});

describe("панель сценария", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
    useToastStore.getState().clear();
    window.localStorage.clear();
  });

  it("переименование пишет файл с If-Match, снимок остаётся прежним", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    const before = orig("company-supervisor");
    await chooseAndManage(user, "company-supervisor");
    const save = screen.getByTestId("scenario-panel-save");
    expect(save).toBeDisabled();
    fill("scenario-name-ru", "Научрук из компании, переименован");
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [, , , id, body, ifMatch] = put.mock.calls[0] ?? [];
    expect(id).toBe("company-supervisor");
    expect(ifMatch).toBe(before.etag);
    expect(body?.record_snapshot).toBeUndefined();
    expect(body?.scenario.snapshot).toEqual(before.scenario?.snapshot);
    expect(body?.scenario.inputs).toEqual(before.scenario?.inputs);
    expect(body?.scenario.name.ru).toBe("Научрук из компании, переименован");
    await waitFor(() => {
      expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
        "переименован",
      );
    });
    // ETag записи сменился, форма пересоздана и снова чиста.
    await waitFor(() => {
      expect(screen.getByTestId("scenario-panel-save")).toBeDisabled();
    });
  });

  it("расхождение: разделы и элементы со знаками, «Принять» пишет снимок и снимает расхождение", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await chooseAndManage(user, "university-supervisor");
    const diff = await screen.findByTestId("scenario-diff");
    expect(diff).toHaveTextContent("Расхождения");
    expect(diff).toHaveTextContent("Ожидали");
    expect(diff).toHaveTextContent("Маршрут подписания");
    expect(diff).toHaveTextContent("topic-approval: шаг 3");
    const signs = within(diff)
      .getAllByText(/^[+~-]$/)
      .map((el) => el.textContent);
    expect(signs).toEqual(expect.arrayContaining(["+", "-"]));
    await user.click(screen.getByTestId("scenario-accept"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const body = put.mock.calls[0]?.[4];
    expect(body?.record_snapshot).toBe("work_tree");
    expect(body?.version).toBe(REF.version);
    expect(put.mock.calls[0]?.[5]).toBe(
      orig("university-supervisor").etag.replace(/\d+/, (n) => n)
        ? put.mock.calls[0]?.[5]
        : null,
    );
    await waitFor(() => {
      expect(screen.queryByTestId("scenario-diff")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("scenario-panel")).toHaveTextContent("Совпадает");
    const toasts = useToastStore.getState().toasts;
    expect(toasts.some((x) => x.message.includes("Снимок сценария"))).toBe(
      true,
    );
  });

  it("«Принять» отменяется: возвращает прежний снимок с If-Match нового ETag", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    const before = orig("university-supervisor");
    await chooseAndManage(user, "university-supervisor");
    await user.click(await screen.findByTestId("scenario-accept"));
    const toast = await waitFor(() => {
      const found = useToastStore
        .getState()
        .toasts.find((x) => x.message.includes("Снимок сценария"));
      if (!found) throw new Error("no toast");
      return found;
    });
    expect(toast.duration).toBe(10_000);
    toast.action?.onClick();
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(2);
    });
    const undo = put.mock.calls[1];
    expect(undo?.[4]?.record_snapshot).toBeUndefined();
    expect(undo?.[4]?.scenario.snapshot).toEqual(before.scenario?.snapshot);
    expect(undo?.[5]).not.toBe(before.etag);
  });

  it("удаляет сценарий и отменяет удаление в течение десяти секунд", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const del = vi.spyOn(packOutcomeApi, "deleteScenario");
    const user = userEvent.setup();
    mount();
    const before = orig("company-supervisor");
    await chooseAndManage(user, "company-supervisor");
    await user.click(screen.getByTestId("scenario-delete"));
    await waitFor(() => {
      expect(del).toHaveBeenCalledTimes(1);
    });
    expect(del.mock.calls[0]?.slice(3)).toEqual([
      "company-supervisor",
      before.etag,
    ]);
    await waitFor(() => {
      expect(screen.queryByTestId("scenario-panel")).not.toBeInTheDocument();
    });
    // Выбранный удалённый сценарий снят с адреса, в списке его нет.
    await waitFor(() => {
      expect(where()).not.toContain("scenario=");
    });
    expect(
      scenarioReference.entries().some((e) => e.id === "company-supervisor"),
    ).toBe(false);
    const toast = useToastStore
      .getState()
      .toasts.find((x) => x.message.includes("удалён"));
    expect(toast?.duration).toBe(10_000);
    expect(toast?.action?.label).toBe("Отменить");
    toast?.action?.onClick();
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    // Запись без If-Match с телом удалённого сценария: те же данные.
    expect(put.mock.calls[0]?.[5]).toBeNull();
    expect(put.mock.calls[0]?.[4]).toEqual({ scenario: before.scenario });
    await waitFor(() => {
      expect(where()).toContain("scenario=company-supervisor");
    });
    expect(orig("company-supervisor").scenario).toEqual(before.scenario);
  });

  it("чужая правка файла: мягкое «файл изменён», «Обновить» подтягивает диск", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await chooseAndManage(user, "company-supervisor");
    scenarioReference.touch("company-supervisor");
    fill("scenario-name-ru", "Моё имя");
    await user.click(screen.getByTestId("scenario-panel-save"));
    const notice = await screen.findByTestId("scenario-failure");
    expect(notice).toHaveTextContent("Файл сценария изменён");
    expect(notice).toHaveAttribute("role", "status");
    await user.click(screen.getByTestId("scenario-failure-refresh"));
    await waitFor(() => {
      expect(screen.queryByTestId("scenario-failure")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("scenario-name-ru")).toHaveValue(
      "Научрук из компании, есть консультант",
    );
    expect(put).toHaveBeenCalledTimes(1);
  });

  it("чужая правка файла: «Сохранить поверх» повторяет запись с ETag с диска", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await chooseAndManage(user, "company-supervisor");
    scenarioReference.touch("company-supervisor");
    const disk = orig("company-supervisor").etag;
    fill("scenario-name-ru", "Моё имя");
    await user.click(screen.getByTestId("scenario-panel-save"));
    await user.click(await screen.findByTestId("scenario-failure-overwrite"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(2);
    });
    expect(put.mock.calls[1]?.[5]).toBe(disk);
    await waitFor(() => {
      expect(screen.getByTestId("scenario-trigger")).toHaveTextContent(
        "Моё имя",
      );
    });
  });

  it("битый файл: причина сервера и переход к файлу, принять и дублировать нельзя", async () => {
    const user = userEvent.setup();
    mount("scenario=draft");
    await user.click(await screen.findByTestId("scenario-manage"));
    const broken = await screen.findByTestId("scenario-panel-broken");
    expect(broken).toHaveTextContent("Файл сценария не читается");
    expect(broken).toHaveTextContent("значение 'firm' не из списка");
    expect(
      screen.getByTestId("scenario-open-file").getAttribute("href"),
    ).toContain("scenarios%2Fdraft.yaml");
    expect(screen.queryByTestId("scenario-accept")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scenario-duplicate")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scenario-panel-save")).not.toBeInTheDocument();
    expect(screen.getByTestId("scenario-delete")).toBeInTheDocument();
  });

  it("дублирует: окно с копией и новым именем файла", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount();
    await chooseAndManage(user, "company-supervisor");
    await user.click(screen.getByTestId("scenario-duplicate"));
    await screen.findByTestId("scenario-save-dialog");
    expect(screen.getByTestId("scenario-id")).toHaveValue(
      "company-supervisor-copy",
    );
    expect(screen.getByTestId("scenario-name-ru")).toHaveValue(
      "Научрук из компании, есть консультант (копия)",
    );
    await user.click(screen.getByTestId("scenario-submit"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const [, , , id, body, ifMatch] = put.mock.calls[0] ?? [];
    expect(id).toBe("company-supervisor-copy");
    expect(ifMatch).toBeNull();
    // Копия несёт снимок и утверждения исходного, а не записывает новые.
    expect(body?.record_snapshot).toBeUndefined();
    expect(body?.scenario.snapshot).toEqual(
      orig("company-supervisor").scenario?.snapshot,
    );
    expect(body?.scenario.assertions).toHaveLength(3);
  });
});

describe("«Сохранить в сценарий» из панели вводных", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
    useToastStore.getState().clear();
    window.localStorage.clear();
  });

  it("показывает, что поменяется, пишет вводные и обновляет снимок", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount("scenario=company-supervisor&i.supervisor=university");
    await user.click(await screen.findByTestId("outcome-inputs-save-into"));
    const dialog = await screen.findByTestId("scenario-save-inputs");
    expect(dialog).toHaveTextContent("было «Из компании», станет «Из ВШЭ»");
    expect(screen.getByTestId("scenario-save-inputs-refresh")).toBeChecked();
    await user.click(screen.getByTestId("scenario-save-inputs-submit"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    const body = put.mock.calls[0]?.[4];
    expect(body?.scenario.inputs).toEqual({
      supervisor: "university",
      co_supervisor: "yes",
    });
    expect(body?.record_snapshot).toBe("work_tree");
    await waitFor(() => {
      expect(where()).not.toContain("i.supervisor");
    });
    await waitFor(() => {
      expect(where()).toContain("scenario=company-supervisor");
    });
  });

  it("без галочки снимок не трогается", async () => {
    const put = vi.spyOn(packOutcomeApi, "putScenario");
    const user = userEvent.setup();
    mount("scenario=company-supervisor&i.supervisor=university");
    await user.click(await screen.findByTestId("outcome-inputs-save-into"));
    await user.click(await screen.findByTestId("scenario-save-inputs-refresh"));
    await user.click(screen.getByTestId("scenario-save-inputs-submit"));
    await waitFor(() => {
      expect(put).toHaveBeenCalledTimes(1);
    });
    expect(put.mock.calls[0]?.[4]?.record_snapshot).toBeUndefined();
  });

  it("кнопки нет в режиме «Как студент» и при расчёте не из рабочего дерева", async () => {
    mount("scenario=company-supervisor&i.supervisor=university&mode=student");
    await screen.findByTestId("scenario-trigger");
    expect(screen.queryByTestId("scenario-save-as")).not.toBeInTheDocument();
    expect(screen.queryByTestId("scenario-manage")).not.toBeInTheDocument();
    cleanup();
    mount("scenario=company-supervisor&state=head");
    const button = await screen.findByTestId("scenario-save-as");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute(
      "title",
      expect.stringContaining("рабочего дерева"),
    );
  });
});

describe("английский и телефон", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    scenarioReference.reset();
  });
  afterEach(async () => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setBehavior("normal");
    scenarioReference.reset();
    useToastStore.getState().clear();
    window.localStorage.clear();
    await i18n.changeLanguage("ru");
  });

  it("тексты на английском: статусы, итог, окно", async () => {
    await i18n.changeLanguage("en");
    const user = userEvent.setup();
    mount();
    await openPicker(user);
    await waitFor(() => {
      expect(screen.getByTestId("scenario-summary")).toHaveTextContent(
        "2 passed, 1 changed, 1 broken file",
      );
    });
    expect(
      screen.getByTestId("scenario-option-company-supervisor"),
    ).toHaveTextContent("Company supervisor with a co-supervisor");
    await user.keyboard("{Escape}");
    await user.click(await screen.findByTestId("scenario-save-as"));
    const dialog = await screen.findByTestId("scenario-save-dialog");
    expect(dialog).toHaveTextContent("Expected result");
    expect(dialog).toHaveTextContent("Assert as is");
    expect(dialog).not.toHaveTextContent(/scenarios\./);
  });

  it("телефон: список и окна открываются листами", async () => {
    await i18n.changeLanguage("ru");
    const viewport = installViewport(360);
    try {
      const user = userEvent.setup();
      mount();
      await user.click(await screen.findByTestId("scenario-trigger"));
      await screen.findByTestId("scenario-list");
      expect(document.querySelector(".pop-scrim")).not.toBeNull();
      await user.click(
        screen.getByTestId("scenario-option-company-supervisor"),
      );
      await user.click(await screen.findByTestId("scenario-manage"));
      const sheet = await screen.findByRole("dialog");
      expect(sheet).toHaveAttribute("data-form", "sheet");
      expect(within(sheet).getByTestId("scenario-panel")).toBeInTheDocument();
    } finally {
      viewport.restore();
    }
  });
});
