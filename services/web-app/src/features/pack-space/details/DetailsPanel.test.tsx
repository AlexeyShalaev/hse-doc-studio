import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { packStudioApi, type PackVersionRef } from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
  referenceManifest,
  resetReferenceManifests,
  setExplainBehavior,
} from "@entities/pack-studio/reference";
import { i18n, useToastStore } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { render } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router";
import { isSpaceTab, type PackTree } from "@entities/pack-studio";
import { SpaceProvider } from "../context/SpaceContext";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../galleryKit";
import { SpaceScreen } from "../shell/SpaceScreen";
import { defineSpaceSlots } from "../shell/spaceSlots";
import { DetailsPanel } from "./DetailsPanel";
import { resetEditFeeds } from "./edit/editFeed";

// Правая колонка «Результата»: четыре состояния, «почему так» без внутренних слов, правка
// условия мини-формой с записью в черновик, отмена и повтор, выпущенная версия. Сервер подменён
// эталонами (reference): те же ответы и манифесты, что у старого экрана.

const WS = "gallery-ws";
const VKR = "/pack-studio/w/gallery-ws/t/hse-cs-se/vkr/2026.1.2";
const VKR_REF: PackVersionRef = {
  pack: "hse-cs-se",
  template: "vkr",
  version: "2026.1.2",
};
const COURSEWORK_REF: PackVersionRef = {
  pack: "hse-cs-sse",
  template: "coursework",
  version: "2026.1.3",
};
const DOC = "sel=documents%3Atechnical_specification";

// Пространство с двумя шаблонами: ВКР (черновик 2026.1.2, выпуск 2026.1.1) и курсовой проект
// (черновик 2026.1.3, выпуск 2026.1.2). `renderSpace` из каркаса держит только курсовой.
const TREE: PackTree = {
  ...GALLERY_TREE,
  packs: [
    ...GALLERY_TREE.packs,
    {
      id: "hse-cs-se",
      path: "hse-cs-se",
      name: { ru: "Программная инженерия" },
      templates: [
        {
          id: "vkr",
          path: "hse-cs-se/templates/vkr",
          name: { ru: "ВКР бакалавра" },
          default_version: "2026.1.1",
          versions: [
            {
              version: "2026.1.1",
              path: "hse-cs-se/templates/vkr/versions/2026.1.1",
              status: "stable",
              released: true,
              modified: false,
            },
            {
              version: "2026.1.2",
              path: "hse-cs-se/templates/vkr/versions/2026.1.2",
              status: "beta",
              released: false,
              modified: false,
            },
          ],
        },
      ],
    },
  ],
};

const Provider = ({ children }: { children: ReactNode }) => {
  const { pack = "", template = "", version = "", tab } = useParams();
  return (
    <SpaceProvider
      workspace={GALLERY_WORKSPACE}
      tree={TREE}
      versionRef={{ pack, template, version }}
      tab={isSpaceTab(tab) ? tab : "result"}
    >
      {children}
    </SpaceProvider>
  );
};

const Probe = () => {
  const { pathname, search } = useLocation();
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const renderSpace = (ui: ReactNode, url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/pack-studio/w/:workspaceId/t/:pack/:template/:version/:tab"
          element={<Provider>{ui}</Provider>}
        />
      </Routes>
      <Probe />
    </MemoryRouter>,
  );

const SPACE_BASE = "/pack-studio/w/gallery-ws/t/hse-cs-sse/coursework";

const kinds = (doc: string) =>
  (
    referenceManifest(WS, VKR_REF, `files/${doc}/doc.yaml`) as {
      supported_kinds: string[];
    }
  ).supported_kinds;

const mount = (url: string, ui: ReactNode = <DetailsPanel />) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  renderSpace(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
    url,
  );
  return client;
};

const location = () => screen.getByTestId("location").textContent ?? "";

describe("«Подробности»", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await loadPackSpaceNamespace();
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    setExplainBehavior("normal");
    resetReferenceManifests();
    resetEditFeeds();
    useToastStore.getState().clear();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    outcomeReference.setSource("reference");
    resetReferenceManifests();
  });

  describe("ничего не выбрано", () => {
    it("объясняет, что здесь можно сделать, вместо пустого «Элемент не выбран»", async () => {
      mount(`${VKR}/result`);
      const panel = await screen.findByTestId("sp-details-empty");
      expect(panel).toHaveTextContent("Что здесь можно сделать");
      expect(panel).toHaveTextContent("Поменяйте условия сверху");
      expect(panel).not.toHaveTextContent("Элемент не выбран");
    });

    it("выбор, которого нет в результате, тоже считается «ничего не выбрано»", async () => {
      mount(`${VKR}/result?sel=unknown%3Aabc`);
      expect(await screen.findByTestId("sp-details-empty")).toBeInTheDocument();
    });
  });

  describe("элемент выбран", () => {
    it("«Почему так» предложениями, без идентификаторов и путей", async () => {
      mount(`${VKR}/result?${DOC}`);
      const why = await screen.findByTestId("sp-why");
      await waitFor(() => {
        expect(within(why).getAllByTestId("sp-why-row").length).toBeGreaterThan(
          0,
        );
      });
      const text = why.textContent ?? "";
      expect(text).toContain("Вид работы");
      expect(text).toMatch(/Входит в комплект, когда вид работы/);
      expect(text).not.toMatch(
        /supported_|doc\.yaml|files\/|technical_specification/,
      );
      expect(screen.getByTestId("sp-details-title")).not.toHaveTextContent(
        "technical_specification",
      );
      expect(screen.getByTestId("sp-details-state")).toHaveTextContent(
        "входит в комплект",
      );
    });

    it("идентификаторы и файлы только в «Технических подробностях»", async () => {
      mount(`${VKR}/result?${DOC}`);
      const tech = await screen.findByTestId("sp-tech");
      expect(tech).not.toHaveAttribute("open");
      expect(tech).toHaveTextContent("documents:technical_specification");
      expect(tech).toHaveTextContent("files/technical_specification/doc.yaml");
      const links = within(tech).getAllByTestId("sp-tech-open");
      expect(links[0]?.getAttribute("href")).toMatch(
        /\/content\?.*file=.*doc\.yaml.*&?at=%2Fsupported_kinds/,
      );
    });

    it("«Что изменится, если…» ставит условие на экран, «Вернуть» его снимает", async () => {
      mount(`${VKR}/result?${DOC}`);
      const rows = await screen.findAllByTestId("sp-whatif-row");
      expect(rows[0]).toHaveTextContent("Если вид работы");
      expect(rows[0]).toHaveTextContent("документа не будет");
      await userEvent.click(rows[0]!);
      expect(location()).toContain("i.kind=research");
      expect(
        await screen.findByTestId("sp-whatif-applied"),
      ).toBeInTheDocument();
      await userEvent.click(screen.getByTestId("sp-whatif-restore"));
      expect(location()).not.toContain("i.kind");
    });

    it("«Текст документа» ведёт в «Содержимое» на этот документ", async () => {
      mount(`${VKR}/result?${DOC}`);
      const link = await screen.findByTestId("sp-open-content");
      expect(link).toHaveTextContent("Текст документа");
      expect(link.getAttribute("href")).toContain(
        "/content?doc=technical_specification",
      );
    });

    it("ответ не пришёл: понятная ошибка и «Повторить»", async () => {
      setExplainBehavior("fail");
      mount(`${VKR}/result?${DOC}`);
      // Сбой сервера повторяется один раз через секунду, потом показывается ошибка.
      const error = await screen.findByTestId(
        "sp-why-error",
        {},
        { timeout: 4000 },
      );
      expect(error).toHaveTextContent("Не удалось узнать, почему так");
      setExplainBehavior("normal");
      await userEvent.click(screen.getByTestId("sp-why-retry"));
      await waitFor(() => {
        expect(screen.queryByTestId("sp-why-error")).toBeNull();
      });
    });
  });

  describe("правка условия", () => {
    const openForm = async () => {
      await userEvent.click(await screen.findByTestId("sp-edit-open"));
      return screen.findByTestId("sp-edit");
    };

    it("мини-форма подписана фразой, чипы пишут в черновик, видна разница", async () => {
      const errors = vi.spyOn(console, "error");
      mount(`${VKR}/result?${DOC}`);
      const form = await openForm();
      expect(form).toHaveTextContent("Документ нужен, когда вид работы:");
      // Отмечено всё: ограничения нет.
      const kindsList = within(form).getAllByTestId("sp-cond-list")[0];
      expect(kindsList).toHaveTextContent("Отмечено всё: ограничения нет.");
      const chip = await within(form).findByRole("checkbox", {
        name: "Проектная",
      });
      expect(chip).toBeChecked();
      await userEvent.click(chip);
      await waitFor(() => {
        expect(kinds("technical_specification")).toEqual(["research"]);
      });
      // Из двух значений отмечено одно: подсказка говорит, что ограничение есть.
      await waitFor(() => {
        expect(kindsList).toHaveTextContent(
          "Ограничение действует: подходит только отмеченное.",
        );
      });
      expect(kindsList).not.toHaveTextContent("ограничения нет");
      const delta = await screen.findByTestId("sp-edit-delta");
      expect(delta).toHaveTextContent("Результат изменился");
      expect(
        within(delta).getAllByTestId("sp-edit-delta-item")[0],
      ).toHaveAttribute("data-symbol", "-");
      expect(delta).toHaveTextContent("Исчезло");
      // Запись ленты идёт из эффекта: React не жалуется на обновление во время отрисовки.
      const complaints = errors.mock.calls.filter((call) =>
        String(call[0]).includes("Cannot update a component"),
      );
      expect(complaints).toEqual([]);
      errors.mockRestore();
    });

    it("«Готово» закрывает форму, правки остаются", async () => {
      mount(`${VKR}/result?${DOC}`);
      const form = await openForm();
      await userEvent.click(
        await within(form).findByRole("checkbox", { name: "Проектная" }),
      );
      await screen.findByTestId("sp-edit-delta");
      await userEvent.click(screen.getByTestId("sp-edit-done"));
      expect(screen.queryByTestId("sp-edit")).toBeNull();
      expect(kinds("technical_specification")).toEqual(["research"]);
    });

    it("«Отменить» откатывает всё, что внесено с открытия формы, и закрывает её", async () => {
      mount(`${VKR}/result?${DOC}`);
      const form = await openForm();
      expect(screen.getByTestId("sp-edit-cancel")).toBeDisabled();
      const before = [...kinds("technical_specification")];
      await userEvent.click(
        await within(form).findByRole("checkbox", { name: "Проектная" }),
      );
      await waitFor(() => {
        expect(kinds("technical_specification")).toEqual(["research"]);
      });
      await waitFor(() => {
        expect(screen.getByTestId("sp-edit-cancel")).toBeEnabled();
      });
      await userEvent.click(screen.getByTestId("sp-edit-cancel"));
      await waitFor(() => {
        expect(screen.queryByTestId("sp-edit")).toBeNull();
      });
      expect(kinds("technical_specification")).toEqual(before);
    });

    it("Ctrl+Z и Ctrl+Shift+Z отменяют и повторяют правку", async () => {
      mount(`${VKR}/result?${DOC}`);
      const form = await openForm();
      await userEvent.click(
        await within(form).findByRole("checkbox", { name: "Проектная" }),
      );
      await screen.findByTestId("sp-edit-delta");
      fireEvent.keyDown(document.body, { key: "z", ctrlKey: true });
      await waitFor(() => {
        expect(kinds("technical_specification")).toEqual([]);
      });
      fireEvent.keyDown(document.body, {
        key: "z",
        ctrlKey: true,
        shiftKey: true,
      });
      await waitFor(() => {
        expect(kinds("technical_specification")).toEqual(["research"]);
      });
    });

    it("«Ещё»: история правок с кнопками «Отменить» и «Повторить»", async () => {
      mount(`${VKR}/result?${DOC}`);
      const form = await openForm();
      await userEvent.click(
        await within(form).findByRole("checkbox", { name: "Проектная" }),
      );
      await screen.findByTestId("sp-edit-delta");
      await userEvent.click(screen.getByTestId("sp-more"));
      await userEvent.click(await screen.findByTestId("sp-more-history"));
      const history = await screen.findByTestId("sp-history");
      expect(history).toHaveTextContent("Виды работы: изменено");
      expect(history).not.toHaveTextContent("supported_kinds");
      await userEvent.click(within(history).getByTestId("sp-history-undo"));
      await waitFor(() => {
        expect(kinds("technical_specification")).toEqual([]);
      });
      await waitFor(() => {
        expect(within(history).getByTestId("sp-history-redo")).toBeEnabled();
      });
    });

    it("условие подписи: список с понятными подписями", async () => {
      mount(
        `${SPACE_BASE}/2026.1.3/result?sel=${encodeURIComponent("route:topic-approval/step/2")}`,
      );
      const form = await openForm();
      const select = await within(form).findByRole("combobox", {
        name: "Подпись нужна:",
      });
      await userEvent.selectOptions(select, "co_supervisor:company");
      await waitFor(() => {
        const slots = (
          referenceManifest(WS, COURSEWORK_REF, "version.yaml") as {
            pack_submission: {
              profiles: { signing_slots: { when: unknown }[] }[];
            };
          }
        ).pack_submission.profiles[0]?.signing_slots;
        expect(slots?.[0]?.when).toEqual({
          person: "co_supervisor",
          role: "company",
        });
      });
    });

    it("условие, которое по месту не правится, не получает кнопки", async () => {
      mount(
        `${SPACE_BASE}/2026.1.3/result?sel=${encodeURIComponent("route:topic-approval")}`,
      );
      expect(await screen.findByTestId("sp-edit-none")).toBeInTheDocument();
      expect(screen.getByTestId("sp-edit-open")).toBeDisabled();
    });

    it("на телефоне правка тоже доступна: шторка с той же кнопкой и формой", async () => {
      mount(
        `${VKR}/result?${DOC}`,
        <SpaceScreen
          phone
          slots={defineSpaceSlots({ details: { result: DetailsPanel } })}
        />,
      );
      const button = await screen.findByTestId("sp-edit-open");
      await waitFor(() => {
        expect(button).toBeEnabled();
      });
      expect(
        document.querySelector(".sp-root[data-phone] .sp-side"),
      ).not.toBeNull();
      await userEvent.click(button);
      expect(await screen.findByTestId("sp-edit")).toBeInTheDocument();
    });
  });

  describe("выпущенная версия", () => {
    it("вместо «Изменить условия» кнопка «Править копию», она создаёт копию и остаётся на экране", async () => {
      const created = vi
        .spyOn(packStudioApi, "createVersion")
        .mockResolvedValue({
          version: {
            pack: "hse-cs-sse",
            template: "coursework",
            version: "2026.1.3",
            path: "hse-cs-sse/templates/coursework/versions/2026.1.3",
          },
          base: "2026.1.2",
          update_class: "patch",
          warnings: [],
        });
      mount(
        `${SPACE_BASE}/2026.1.2/result?${DOC}&i.kind=project`.replace(
          "technical_specification",
          "project_proposal",
        ),
      );
      const button = await screen.findByTestId("sp-make-copy");
      expect(screen.queryByTestId("sp-edit-open")).toBeNull();
      // Главная кнопка «Править копию» одна, в полосе пространства; здесь вторичная, а
      // слова «выпущена и не меняется» живут в плашке над условиями, не в панели.
      expect(button).not.toHaveClass("primary");
      expect(screen.queryByTestId("sp-released-note")).toBeNull();
      await userEvent.click(button);
      await waitFor(() => {
        expect(created).toHaveBeenCalledWith(
          expect.anything(),
          "hse-cs-sse",
          "coursework",
          { base: "2026.1.2", update_class: "patch" },
        );
      });
      await waitFor(() => {
        expect(location()).toContain("/2026.1.3/result");
      });
      // Условия и выбранный элемент не потерялись.
      expect(location()).toContain("i.kind=project");
      expect(location()).toContain("sel=documents%3Aproject_proposal");
    });
  });

  it("английский текст без ключей словаря", async () => {
    await i18n.changeLanguage("en");
    mount(`${VKR}/result?${DOC}`);
    const why = await screen.findByTestId("sp-why");
    await waitFor(() => {
      expect(within(why).getAllByTestId("sp-why-row").length).toBeGreaterThan(
        0,
      );
    });
    expect(screen.getByTestId("sp-details").textContent).not.toMatch(
      /\bdetails\.[a-z]/,
    );
    await act(async () => {
      await i18n.changeLanguage("ru");
    });
  });
});
