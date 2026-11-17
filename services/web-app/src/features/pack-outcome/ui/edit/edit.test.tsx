import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router";
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
  packStudioApi,
  packStudioKeys,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
  referenceManifest,
  resetReferenceManifests,
  setExplainBehavior,
  touchReferenceManifest,
} from "@entities/pack-studio/reference";
import { ApiError } from "@shared/api";
import { i18n, useToastStore } from "@shared/lib";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../../OutcomeBody";

// Правка правила по месту на экране «Результат»: мини-форма в панели, запись точечными правками
// с If-Match, пересчёт и сравнение, отмена и повтор, мягкое удаление. Сервер подменён
// эталонами (reference/manifests.ts: манифесты версии, PATCH /model, игрушечный пересчёт).

const WS = "ws-edit";
const VKR: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const COURSEWORK: PackVersionRef = {
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

const version = (v: string, dir: string, released = false) => ({
  version: v,
  path: `${dir}/${v}`,
  status: "beta" as const,
  released,
  modified: false,
});

const makeTree = (released: boolean): PackTree => ({
  workspace_id: WS,
  base_sha: null,
  packs: [
    {
      id: "hse-cs-se",
      path: "hse-cs-se",
      name: { ru: "ФКН, Программная инженерия" },
      templates: [
        {
          id: "vkr",
          path: "hse-cs-se/templates/vkr",
          name: { ru: "ВКР бакалавра" },
          default_version: "2026.1.2",
          versions: [
            version("2026.1.2", "hse-cs-se/templates/vkr/versions", released),
          ],
        },
      ],
    },
    {
      id: "hse-cs-sse",
      path: "hse-cs-sse",
      name: { ru: "ФКН, Системная и программная инженерия" },
      templates: [
        {
          id: "coursework",
          path: "hse-cs-sse/templates/coursework",
          name: { ru: "Курсовой проект" },
          default_version: "2026.1.6",
          versions: [
            version("2026.1.6", "hse-cs-sse/templates/coursework/versions"),
          ],
        },
      ],
    },
  ],
  files: [],
  truncated: false,
});

let navigate: ReturnType<typeof useNavigate>;
const Probe = () => {
  const { pathname, search } = useLocation();
  const go = useNavigate();
  useEffect(() => {
    navigate = go;
  }, [go]);
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const Screen = () => {
  const { pack = "", template = "", version = "" } = useParams();
  return (
    <OutcomeBody workspace={workspace} version={{ pack, template, version }} />
  );
};

const pathOf = (ref: PackVersionRef) =>
  `/pack-studio/w/${WS}/result/${ref.pack}/${ref.template}/${ref.version}`;

const mount = (
  search: string,
  ref: PackVersionRef = VKR,
  options: { released?: boolean } = {},
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  client.setQueryData(
    packStudioKeys.tree(WS),
    makeTree(options.released === true),
  );
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`${pathOf(ref)}?${search}`]}>
        <Routes>
          <Route
            path="/pack-studio/w/:workspaceId/result/:pack/:template/:version"
            element={<Screen />}
          />
        </Routes>
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

const DOC = "selected=documents:technical_specification";
const STEP = "selected=route:topic-approval/step/2";

const openEditor = async (traceId: string) => {
  const button = await screen.findByTestId(`outcome-chain-${traceId}-edit`);
  await userEvent.click(button);
  return screen.findByTestId(`outcome-edit-${traceId}`);
};

const delta = () => screen.findByTestId("outcome-edit-delta");
const kinds = (ref: PackVersionRef, doc: string) =>
  (
    referenceManifest(WS, ref, `files/${doc}/doc.yaml`) as {
      supported_kinds: string[];
    }
  ).supported_kinds;
const slots = () =>
  (
    referenceManifest(WS, COURSEWORK, "version.yaml") as {
      pack_submission: { profiles: { signing_slots: unknown[] }[] };
    }
  ).pack_submission.profiles[0]?.signing_slots;
const ctrlZ = (shift = false) => {
  fireEvent.keyDown(document.body, {
    key: "z",
    ctrlKey: true,
    shiftKey: shift,
  });
};

describe("правка правила по месту", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([
      loadPackOutcomeNamespace(),
      loadPackStudioNamespace(),
      loadPackFormsNamespace(),
    ]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    setExplainBehavior("normal");
    resetReferenceManifests();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setSource("reference");
    resetReferenceManifests();
    window.localStorage.clear();
  });

  describe("виды правил", () => {
    it("виды работы документа: набор галочек, запись, дельта «минус документ»", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      const chip = await within(editor).findByRole("checkbox", {
        name: "Проектная",
      });
      expect(chip).toBeChecked();
      await userEvent.click(chip);
      // Записано точечной правкой манифеста документа.
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
      });
      const bar = await delta();
      expect(bar).toHaveTextContent("Результат изменился");
      expect(
        within(bar).getByTestId("outcome-edit-delta-tally"),
      ).toHaveTextContent("+0~0\u22121");
      expect(
        within(bar).getAllByTestId("outcome-edit-delta-item")[0],
      ).toHaveAttribute("data-symbol", "-");
    });

    it("условие слота подписи: список условий, правка и откат Ctrl+Z", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      const select = await within(editor).findByRole("combobox", {
        name: "Условие слота",
      });
      expect(select).toHaveValue("co_supervisor");
      await userEvent.selectOptions(select, "co_supervisor:company");
      await waitFor(() => {
        expect(slots()?.[0]).toMatchObject({
          when: { person: "co_supervisor", role: "company" },
        });
      });
      const bar = await delta();
      // Пара ушла из маршрута: минус, шаг изменился.
      expect(
        within(bar).getAllByTestId("outcome-edit-delta-item").length,
      ).toBeGreaterThan(0);
      expect(bar.querySelector('[data-symbol="-"]')).not.toBeNull();

      ctrlZ();
      await waitFor(() => {
        expect(slots()?.[0]).toMatchObject({
          when: { person: "co_supervisor" },
        });
      });
      expect((slots()?.[0] as { when: Record<string, unknown> }).when).toEqual({
        person: "co_supervisor",
      });
      await waitFor(() => {
        expect(
          screen
            .getByTestId("outcome-edit-delta")
            .querySelector('[data-symbol="+"]'),
        ).not.toBeNull();
      });
      expect(screen.getByTestId("outcome-edit-live")).toHaveTextContent(
        /Результат изменился|Отменено/,
      );
    });

    it("условие «всегда» убирает ключ when, возврат Ctrl+Shift+Z пишет его снова", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      const select = await within(editor).findByRole("combobox", {
        name: "Условие слота",
      });
      await userEvent.selectOptions(select, "always");
      await waitFor(() => {
        expect(slots()?.[0]).not.toHaveProperty("when");
      });
      ctrlZ();
      await waitFor(() => {
        expect(slots()?.[0]).toHaveProperty("when");
      });
      ctrlZ(true);
      await waitFor(() => {
        expect(slots()?.[0]).not.toHaveProperty("when");
      });
    });

    it("условие показа поля анкеты: поле и значение", async () => {
      mount("selected=forms:ai_declaration/tools");
      const editor = await openEditor("t62");
      const field = await within(editor).findByRole("combobox", {
        name: "Показывать, когда",
      });
      expect(field).toHaveValue("used_ai");
      await userEvent.selectOptions(field, "");
      await waitFor(() => {
        const forms = (
          referenceManifest(WS, VKR, "version.yaml") as {
            forms: { sections: { fields: Record<string, unknown>[] }[] }[];
          }
        ).forms;
        expect(forms[0]?.sections[0]?.fields[1]).not.toHaveProperty(
          "visible_if",
        );
      });
    });

    it("порядок подписания целиком: кнопки правки нет, остаётся «Открыть правило»", async () => {
      mount("selected=route:topic-approval", COURSEWORK);
      await screen.findByTestId("outcome-chain-t13-open");
      expect(screen.queryByTestId("outcome-chain-t13-edit")).toBeNull();
    });
  });

  describe("отмена и повтор", () => {
    it("кнопки с подписями, лента правок, состояние после отмены и повтора", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      const undo = screen.getByRole("button", { name: "Отменить" });
      const redo = screen.getByRole("button", { name: "Повторить" });
      expect(undo).toBeEnabled();
      expect(redo).toBeDisabled();
      const entries = screen.getAllByTestId("outcome-edit-entry");
      expect(entries).toHaveLength(1);
      expect(entries[0]).toHaveTextContent("Виды работы документа");
      expect(entries[0]).toHaveTextContent("technical_specification");
      expect(entries[0]).toHaveAttribute("data-state", "applied");

      await userEvent.click(undo);
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual([]);
      });
      expect(screen.getByTestId("outcome-edit-live")).toHaveTextContent(
        /Отменено|Результат/,
      );
      await waitFor(() => {
        expect(screen.getAllByTestId("outcome-edit-entry")[0]).toHaveAttribute(
          "data-state",
          "undone",
        );
      });
      expect(screen.getByRole("button", { name: "Повторить" })).toBeEnabled();
      await userEvent.click(screen.getByRole("button", { name: "Повторить" }));
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
      });
    });

    it("Ctrl+Z внутри текстового поля остаётся за полем", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      const input = document.createElement("input");
      document.body.append(input);
      input.focus();
      fireEvent.keyDown(input, { key: "z", ctrlKey: true });
      await act(async () => {
        await Promise.resolve();
      });
      expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
      input.remove();
    });

    it("версия сменилась: стек правок сбрасывается", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      expect(screen.getByTestId("outcome-edit-bar")).toBeInTheDocument();
      act(() => {
        void navigate(`${pathOf(COURSEWORK)}?${STEP}`);
      });
      await screen.findByTestId("outcome-chain-t14-edit");
      expect(screen.queryByTestId("outcome-edit-bar")).toBeNull();
      ctrlZ();
      await act(async () => {
        await Promise.resolve();
      });
      expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
    });

    it("откат при изменённой записи предупреждает и ждёт согласия", async () => {
      const client = mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      const select = await within(editor).findByRole("combobox", {
        name: "Условие слота",
      });
      await userEvent.selectOptions(select, "co_supervisor:company");
      await delta();
      // Запись поменяли мимо экрана.
      touchReferenceManifest(WS, COURSEWORK, "version.yaml", (data) => {
        const profile = (
          data.pack_submission as {
            profiles: { signing_slots: { when: unknown }[] }[];
          }
        ).profiles[0];
        if (profile)
          profile.signing_slots[0] = {
            ...profile.signing_slots[0],
            when: { person: "supervisor" },
          };
      });
      await waitFor(() => {
        expect(
          (slots()?.[0] as { when: Record<string, unknown> }).when,
        ).toEqual({ person: "supervisor" });
      });
      // Экран перечитал модель (ETag и значение новые): откат видит, что запись уже не та.
      await act(async () => {
        await client.invalidateQueries({
          queryKey: packStudioKeys.model(WS, COURSEWORK),
        });
      });
      ctrlZ();
      const notice = await screen.findByTestId("outcome-edit-notice");
      expect(notice).toHaveTextContent("Запись изменилась после этой правки");
      expect((slots()?.[0] as { when: Record<string, unknown> }).when).toEqual({
        person: "supervisor",
      });
      await userEvent.click(screen.getByTestId("outcome-edit-force"));
      await waitFor(() => {
        expect(
          (slots()?.[0] as { when: Record<string, unknown> }).when,
        ).toEqual({ person: "co_supervisor" });
      });
    });
  });

  describe("точный откат", () => {
    it("файл не трогали после правки: возвращается прежний текст целиком, одним PUT с If-Match", async () => {
      const write = vi.spyOn(packStudioApi, "writeFile");
      const patch = vi.spyOn(packStudioApi, "patchVersionModel");
      mount(DOC);
      const editor = await openEditor("t1");
      const original = JSON.stringify(
        referenceManifest(WS, VKR, "files/technical_specification/doc.yaml"),
      );
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      expect(patch).toHaveBeenCalledTimes(1);
      ctrlZ();
      await waitFor(() => {
        expect(write).toHaveBeenCalledTimes(1);
      });
      const [, path, text, ifMatch] = write.mock.calls[0] ?? [];
      expect(path).toBe(
        "hse-cs-se/templates/vkr/versions/2026.1.2/files/technical_specification/doc.yaml",
      );
      expect(text).toBe(original);
      expect(ifMatch).toMatch(/^"m-\d+"$/);
      await waitFor(() => {
        expect(
          JSON.stringify(
            referenceManifest(
              WS,
              VKR,
              "files/technical_specification/doc.yaml",
            ),
          ),
        ).toBe(original);
      });
      // Повтор идёт правкой значения и снова даёт тот же результат.
      await userEvent.click(
        await screen.findByRole("button", { name: "Повторить" }),
      );
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
      });
      expect(patch).toHaveBeenCalledTimes(2);
      // Следующий откат снова точный.
      ctrlZ();
      await waitFor(() => {
        expect(write).toHaveBeenCalledTimes(2);
      });
    });

    it("файл тронули в другом месте: откат правкой значения, чужое изменение остаётся", async () => {
      const write = vi.spyOn(packStudioApi, "writeFile");
      const patch = vi.spyOn(packStudioApi, "patchVersionModel");
      const client = mount(DOC);
      const editor = await openEditor("t1");
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      touchReferenceManifest(
        WS,
        VKR,
        "files/technical_specification/doc.yaml",
        (data) => {
          data.supported_langs = ["ru"];
        },
      );
      await act(async () => {
        await client.invalidateQueries({
          queryKey: packStudioKeys.model(WS, VKR),
        });
      });
      ctrlZ();
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual([]);
      });
      expect(write).not.toHaveBeenCalled();
      expect(patch).toHaveBeenCalledTimes(2);
      expect(
        (
          referenceManifest(
            WS,
            VKR,
            "files/technical_specification/doc.yaml",
          ) as {
            supported_langs: string[];
          }
        ).supported_langs,
      ).toEqual(["ru"]);
    });
  });

  describe("конфликт при откате", () => {
    it("файл изменили, модель экрана старая: откат получает stale_file и мягко предупреждает", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      await userEvent.selectOptions(
        await within(editor).findByRole("combobox", { name: "Условие слота" }),
        "co_supervisor:company",
      );
      await delta();
      touchReferenceManifest(WS, COURSEWORK, "version.yaml", (data) => {
        data.langs = ["ru"];
      });
      ctrlZ();
      const notice = await screen.findByTestId("outcome-edit-notice");
      expect(notice).toHaveTextContent("Файл изменили, пока вы правили");
      // Правка осталась в силе: курсор не сдвинулся.
      expect(screen.getAllByTestId("outcome-edit-entry")[0]).toHaveAttribute(
        "data-state",
        "applied",
      );
    });
  });

  describe("мягкое удаление", () => {
    it("слот: сводка по трассе, удаление, «Отменить» в тосте на 10 секунд", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      expect(slots()).toHaveLength(2);
      await userEvent.click(
        await within(editor).findByTestId("outcome-edit-t14-delete"),
      );
      const confirm = await screen.findByTestId("outcome-edit-confirm");
      expect(confirm).toHaveTextContent("Удалить: слот подписи?");
      expect(screen.getByTestId("outcome-edit-affected")).toHaveTextContent(
        /Затрагивает \d+ элемент/,
      );
      // Ничего не записано, пока нет согласия.
      expect(slots()).toHaveLength(2);
      await userEvent.click(screen.getByTestId("outcome-edit-confirm-yes"));
      await waitFor(() => {
        expect(slots()).toHaveLength(1);
      });
      const toast = await waitFor(() => {
        const found = useToastStore
          .getState()
          .toasts.find((x) => x.message.includes("Удалено"));
        if (!found) throw new Error("no toast");
        return found;
      });
      expect(toast.duration).toBe(10_000);
      expect(toast.action?.label).toBe("Отменить");
      // След в ленте правок остаётся.
      expect(screen.getAllByTestId("outcome-edit-entry")[0]).toHaveTextContent(
        "Удалено: слот подписи",
      );
      await act(async () => {
        toast.action?.onClick();
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(slots()).toHaveLength(2);
      });
      expect(slots()?.[0]).toMatchObject({ slot_id: "co_supervisor" });
    });

    it("«Не удалять» ничего не пишет", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      await userEvent.click(
        await within(editor).findByTestId("outcome-edit-t14-delete"),
      );
      await userEvent.click(
        await screen.findByTestId("outcome-edit-confirm-no"),
      );
      expect(screen.queryByTestId("outcome-edit-confirm")).toBeNull();
      expect(slots()).toHaveLength(2);
    });

    it("Escape в подтверждении отменяет, не закрывая правку", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      await userEvent.click(
        await within(editor).findByTestId("outcome-edit-t14-remove"),
      );
      const confirm = await screen.findByTestId("outcome-edit-confirm");
      fireEvent.keyDown(confirm, { key: "Escape" });
      expect(screen.queryByTestId("outcome-edit-confirm")).toBeNull();
      expect(screen.getByTestId("outcome-edit-t14")).toBeInTheDocument();
    });

    it("убрать условие: тост с отменой возвращает значение", async () => {
      mount(STEP, COURSEWORK);
      const editor = await openEditor("t14");
      await userEvent.click(
        await within(editor).findByTestId("outcome-edit-t14-remove"),
      );
      await userEvent.click(
        await screen.findByTestId("outcome-edit-confirm-yes"),
      );
      await waitFor(() => {
        expect(slots()?.[0]).not.toHaveProperty("when");
      });
      const toast = useToastStore
        .getState()
        .toasts.find((x) => x.message.includes("Условие убрано"));
      expect(toast).toBeDefined();
      await act(async () => {
        toast?.action?.onClick();
        await Promise.resolve();
      });
      await waitFor(() => {
        expect((slots()?.[0] as { when: unknown }).when).toEqual({
          person: "co_supervisor",
        });
      });
    });
  });

  describe("отказы записи", () => {
    it("чужая правка файла (stale_file): плашка, запись не попала в ленту", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      const chip = await within(editor).findByRole("checkbox", {
        name: "Проектная",
      });
      touchReferenceManifest(
        WS,
        VKR,
        "files/technical_specification/doc.yaml",
        (data) => {
          data.supported_langs = ["ru"];
        },
      );
      await userEvent.click(chip);
      const notice = await screen.findByTestId("outcome-edit-notice");
      expect(notice).toHaveTextContent("Файл изменили, пока вы правили");
      expect(kinds(VKR, "technical_specification")).toEqual([]);
      expect(screen.queryByTestId("outcome-edit-entry")).toBeNull();
      // Модель перечитана: повтор правки проходит.
      await waitFor(() => {
        expect(
          within(screen.getByTestId("outcome-edit-t1")).getByRole("checkbox", {
            name: "Проектная",
          }),
        ).toBeEnabled();
      });
      await userEvent.click(screen.getByText("Понятно"));
      await userEvent.click(
        within(screen.getByTestId("outcome-edit-t1")).getByRole("checkbox", {
          name: "Проектная",
        }),
      );
      await waitFor(() => {
        expect(kinds(VKR, "technical_specification")).toEqual(["research"]);
      });
    });

    it("ошибка схемы: текст сервера и причина", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      const chip = await within(editor).findByRole("checkbox", {
        name: "Проектная",
      });
      vi.spyOn(packStudioApi, "patchVersionModel").mockRejectedValueOnce(
        new ApiError("Правка не по схеме.", "model_invalid", 422, {
          reason: "unknown key supported_kind",
        }),
      );
      await userEvent.click(chip);
      const notice = await screen.findByTestId("outcome-edit-notice");
      expect(notice).toHaveTextContent("Правку формы нельзя записать");
      expect(notice).toHaveTextContent("unknown key supported_kind");
      expect(kinds(VKR, "technical_specification")).toEqual([]);
    });
  });

  describe("неизменяемая версия и ограничения", () => {
    it("выпущенная версия: кнопка неактивна, объяснение и ссылка на мастер новой версии", async () => {
      mount(DOC, VKR, { released: true });
      const button = await screen.findByTestId("outcome-chain-t1-edit");
      expect(button).toBeDisabled();
      expect(screen.getByTestId("outcome-chain-t1-edit-why")).toHaveTextContent(
        "Версия выпущена и неизменяема",
      );
      const link = screen.getByTestId("outcome-chain-t1-new-version");
      expect(link).toHaveAttribute(
        "href",
        "/pack-studio/w/ws-edit?view=files&newVersion=hse-cs-se%2Fvkr",
      );
      await userEvent.click(button);
      expect(screen.queryByTestId("outcome-edit-t1")).toBeNull();
    });

    it("не рабочее дерево: правка отключена с объяснением", async () => {
      mount(`${DOC}&state=head`);
      const button = await screen.findByTestId("outcome-chain-t1-edit");
      expect(button).toBeDisabled();
      expect(screen.getByTestId("outcome-chain-t1-edit-why")).toHaveTextContent(
        "Править можно только рабочее дерево",
      );
    });

    it("«Как студент»: панели правил нет, правки нет", async () => {
      mount(`${DOC}&mode=student`);
      await screen.findByTestId("outcome-screen");
      expect(screen.queryByTestId("outcome-chain-t1-edit")).toBeNull();
    });

    it("зашитое в движок правило: кнопки правки нет", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain-t22-edit");
      expect(screen.queryByTestId("outcome-chain-t24-edit")).toBeNull();
    });
  });

  describe("клавиатура и доступность", () => {
    it("Escape закрывает мини-форму, фокус остаётся на кнопке правки", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      // Форма открыта: фокус внутри неё.
      await waitFor(() => {
        expect(editor).toHaveFocus();
      });
      fireEvent.keyDown(editor, { key: "Escape" });
      expect(screen.queryByTestId("outcome-edit-t1")).toBeNull();
      expect(screen.getByTestId("outcome-chain-t1-edit")).toHaveFocus();
      expect(screen.getByTestId("outcome-chain-t1-edit")).toHaveAttribute(
        "aria-expanded",
        "false",
      );
    });

    it("кнопка правки раскрывает форму и сообщает состояние", async () => {
      mount(DOC);
      const button = await screen.findByTestId("outcome-chain-t1-edit");
      expect(button).toHaveAttribute("aria-expanded", "false");
      await userEvent.click(button);
      expect(button).toHaveAttribute("aria-expanded", "true");
      expect(
        await screen.findByRole("group", { name: "Правка правила" }),
      ).toBeInTheDocument();
    });

    it("после правки объявление в aria-live", async () => {
      mount(DOC);
      const editor = await openEditor("t1");
      await userEvent.click(
        await within(editor).findByRole("checkbox", { name: "Проектная" }),
      );
      await delta();
      const live = screen.getByTestId("outcome-edit-live");
      expect(live).toHaveAttribute("aria-live", "polite");
      expect(live).toHaveTextContent("Результат изменился");
    });
  });

  describe("язык", () => {
    it("английские тексты формы, ленты и сравнения", async () => {
      await i18n.changeLanguage("en");
      try {
        mount(DOC);
        const button = await screen.findByTestId("outcome-chain-t1-edit");
        expect(button).toHaveTextContent("Edit rule");
        await userEvent.click(button);
        const editor = await screen.findByTestId("outcome-edit-t1");
        await userEvent.click(
          await within(editor).findByRole("checkbox", { name: "Project" }),
        );
        const bar = await delta();
        expect(bar).toHaveTextContent("The outcome changed");
        expect(
          screen.getByRole("button", { name: "Undo" }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: "Redo" }),
        ).toBeInTheDocument();
        expect(screen.getByTestId("outcome-edit-history")).toHaveTextContent(
          "Edit history (1)",
        );
      } finally {
        await i18n.changeLanguage("ru");
      }
    });
  });

  describe("телефон", () => {
    let viewport: ReturnType<typeof installViewport>;
    beforeEach(() => {
      viewport = installViewport(360);
    });
    afterEach(() => {
      viewport.restore();
    });

    it("на странице «Почему?» правило читается, но править нельзя", async () => {
      mount(`tab=rules&${DOC}`);
      const sheet = await screen.findByTestId("outcome-rules-page");
      await within(sheet).findByTestId("outcome-chain");
      expect(within(sheet).queryByTestId("outcome-chain-t1-edit")).toBeNull();
      expect(within(sheet).queryByTestId("outcome-edit-bar")).toBeNull();
    });
  });
});
