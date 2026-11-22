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
import { MemoryRouter, useLocation, useNavigate } from "react-router";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  packOutcomeKeys,
  packStudioKeys,
  type PackOutcomeExplain,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  installOutcomeReference,
  outcomeReference,
  realExplains,
  setExplainBehavior,
} from "@entities/pack-studio/reference";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { installViewport } from "@shared/lib/viewport/testing";
import { OutcomeBody } from "../OutcomeBody";

// Правая панель «Правила и причины» на эталонах контракта и настоящих ответах `explain`
// (reference/explainReal.json: ответы ядра на ВКР и курсовой проекте из репозитория).

const WS = "ws-rules";
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

const version = (v: string, dir: string) => ({
  version: v,
  path: `${dir}/${v}`,
  status: "beta" as const,
  released: false,
  modified: false,
});

const tree: PackTree = {
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
          versions: [version("2026.1.2", "hse-cs-se/templates/vkr/versions")],
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
};

let navigate: ReturnType<typeof useNavigate>;
const Probe = () => {
  const { pathname, search } = useLocation();
  const go = useNavigate();
  useEffect(() => {
    navigate = go;
  }, [go]);
  return <output data-testid="location">{`${pathname}${search}`}</output>;
};

const pathOf = (ref: PackVersionRef) =>
  `/pack-studio/w/${WS}/result/${ref.pack}/${ref.template}/${ref.version}`;

const mount = (
  search = "",
  ref: PackVersionRef = VKR,
  seed?: (client: QueryClient) => void,
) => {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, retryDelay: 0 },
    },
  });
  client.setQueryData(packStudioKeys.tree(WS), tree);
  seed?.(client);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[`${pathOf(ref)}${search ? `?${search}` : ""}`]}
      >
        <OutcomeBody workspace={workspace} version={ref} />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
};

const location = () => screen.getByTestId("location").textContent;
// Ответ «Почему?» пришёл: состояние элемента на месте (заголовок рисуется сразу, по id).
const why = () => screen.findByTestId("outcome-why-state");
const title = (text: string) =>
  waitFor(() => {
    expect(screen.getByTestId("outcome-why-title")).toHaveTextContent(text);
  });
const chain = () => screen.getByTestId("outcome-chain");
const chainItems = () => within(chain()).getAllByRole("listitem");

describe("панель «Правила и причины»: «Почему?»", () => {
  beforeAll(async () => {
    installOutcomeReference();
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  beforeEach(() => {
    window.localStorage.clear();
    outcomeReference.setSource("reference");
    setExplainBehavior("normal");
  });
  afterEach(() => {
    cleanup();
    outcomeReference.setSource("reference");
    outcomeReference.setBehavior("normal");
    setExplainBehavior("normal");
    window.localStorage.clear();
  });

  describe("все типы элементов на настоящих ответах", () => {
    it("документ выключен: цепочка, правило движка, что если", async () => {
      mount("selected=documents:operator_manual");
      await why();
      await title("Руководство оператора");
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent(
        "выключен",
      );
      const items = chainItems();
      expect(items).toHaveLength(4);
      expect(items.map((li) => li.getAttribute("data-status"))).toEqual([
        "held",
        "held",
        "not_held",
        "held",
      ]);
      // Исход словами, не только цветом.
      expect(items[2]).toHaveTextContent("Не выполнено");
      expect(items[0]).toHaveTextContent("Выполнено");
      // Условие и факт человеческой фразой.
      expect(items[0]).toHaveTextContent("вид работы: нужно проектный");
      expect(items[0]).toHaveTextContent("Сейчас:");
      expect(items[0]).toHaveTextContent("проектный");
      expect(within(items[2]!).getByTestId(/builtin$/)).toHaveTextContent(
        "в движке",
      );
      expect(items[2]).toHaveTextContent("Только программиста");
      // Правило манифеста: файл, указатель и кнопки перехода.
      expect(items[0]).toHaveTextContent("files/operator_manual/doc.yaml");
      expect(items[0]).toHaveTextContent("/supported_kinds");
      expect(screen.getByTestId("outcome-chain-t22-open")).toBeInTheDocument();
      expect(
        screen.getByTestId("outcome-chain-t22-source"),
      ).toBeInTheDocument();
      expect(screen.queryByTestId("outcome-chain-t24-open")).toBeNull();
      expect(
        within(screen.getByTestId("outcome-whatif"))
          .getAllByRole("button")
          .map((b) => b.textContent),
      ).toHaveLength(3);
    });

    it("документ в комплекте: три выполненных решения", async () => {
      mount("selected=documents:technical_specification");
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent(
        "в комплекте",
      );
      expect(chainItems()).toHaveLength(3);
      expect(
        chainItems().every((li) => li.getAttribute("data-status") === "held"),
      ).toBe(true);
    });

    it("поле анкеты скрыто: условие visible_if не выполнено", async () => {
      mount("selected=forms:ai_declaration/tools");
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("нет");
      const [item] = chainItems();
      expect(item).toHaveAttribute("data-status", "not_held");
      expect(item).toHaveTextContent("Условие показа поля");
      expect(item).toHaveTextContent("version.yaml");
    });

    it("поле проекта без правил: спокойный текст, не ошибка", async () => {
      mount("selected=meta:year");
      await why();
      expect(screen.getByTestId("outcome-chain-empty")).toHaveTextContent(
        "Отдельных правил у этого элемента нет.",
      );
      expect(screen.getByTestId("outcome-chain-empty")).toHaveTextContent(
        "От вводных он не зависит.",
      );
      expect(screen.queryByTestId("outcome-why-error")).toBeNull();
    });

    it("отсутствующий участник: пустая цепочка и что если", async () => {
      mount("selected=participants:co_supervisor");
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("нет");
      expect(screen.getByTestId("outcome-chain-empty")).toHaveTextContent(
        "меняют вводные",
      );
      expect(
        screen.getByTestId("outcome-whatif-co_supervisor-yes"),
      ).toHaveTextContent("Если «второй руководитель»: да");
    });

    it("точка сдачи и дополнительный файл: пустая цепочка без ошибки", async () => {
      mount("selected=points:checkpoint-1");
      await why();
      expect(screen.getByTestId("outcome-chain-empty")).toBeInTheDocument();
      cleanup();
      mount("selected=points:final/.hse-studio/forms/ai_declaration.json");
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("есть");
    });

    it("маршрут точки: порядок, соседи, переход выбирает элемент", async () => {
      mount("selected=route:checkpoint-1");
      await why();
      const [item] = chainItems();
      expect(item).toHaveTextContent("Порядок подписания");
      expect(item).toHaveTextContent("Условий нет");
      const readers = screen.getByTestId("outcome-readers");
      const buttons = within(readers).getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(1);
      fireEvent.click(buttons[0]!);
      expect(location()).toMatch(/selected=/);
      expect(location()).not.toContain("selected=route%3Acheckpoint-1&");
    });

    it("шаг маршрута: заметка про порядок и пары", async () => {
      mount("selected=route:pdp-application/step/1");
      await why();
      await title("Шаг 1");
      expect(screen.getByTestId("outcome-why-step-note")).toHaveTextContent(
        "порядок маршрута",
      );
      expect(chainItems().length).toBeGreaterThan(0);
    });

    it("пара документ и слот", async () => {
      mount("selected=route:pdp-application/pdp_assignment/supervisor");
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("есть");
      expect(screen.getByTestId("outcome-chain-empty")).toBeInTheDocument();
    });

    it("пропущенная пара курсовой: слот не добавлен условием when", async () => {
      mount(
        "selected=route:topic-approval/topic_application/co_supervisor&i.supervisor=university&i.co_supervisor=no&i.academic_supervisor=yes",
        COURSEWORK,
      );
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("нет");
      const [item] = chainItems();
      expect(item).toHaveAttribute("data-status", "not_held");
      expect(item).toHaveTextContent("Условие слота подписи");
      expect(item).toHaveTextContent("второй руководитель указано");
      expect(item).toHaveTextContent(
        "/pack_submission/profiles/0/signing_slots/0/when",
      );
      expect(
        screen.getByTestId("outcome-whatif-co_supervisor-yes"),
      ).toBeInTheDocument();
    });

    it("правило проверки", async () => {
      mount("selected=checks:gost-7.32-2017/page-margins");
      await why();
      await title("Поля страницы");
    });

    it("анкета и точка курсовой на реальных ответах", async () => {
      mount("selected=forms:code_link", COURSEWORK);
      await why();
      expect(screen.getByTestId("outcome-why-state")).toHaveTextContent("есть");
    });
  });

  describe("у каждого настоящего ответа открывается цепочка", () => {
    it("все ответы ядра: статусы словами, число пунктов, что если, соседи", async () => {
      for (const set of realExplains()) {
        const ref = set.set.startsWith("vkr") ? VKR : COURSEWORK;
        const overrides = set.set.endsWith("_alt")
          ? Object.entries(set.inputs)
              .filter(([k]) =>
                [
                  "kind",
                  "staffing",
                  "supervisor",
                  "co_supervisor",
                  "academic_supervisor",
                ].includes(k),
              )
              .map(([k, v]) => `i.${k}=${v}`)
              .join("&")
          : "";
        const inputs = Object.fromEntries(
          overrides
            .split("&")
            .filter(Boolean)
            .map((pair) => {
              const [k, v] = pair.slice(2).split("=");
              return [k, v];
            }),
        ) as Record<string, string>;
        const client = mount(overrides, ref, (c) => {
          for (const [key, body] of Object.entries(set.elements)) {
            const [section, ...rest] = key.split(":");
            c.setQueryData(
              packOutcomeKeys.explain(WS, ref, {
                state: "work_tree",
                ...(Object.keys(inputs).length > 0 ? { inputs } : {}),
                element: {
                  section: section as PackOutcomeExplain["element"]["section"],
                  id: rest.join(":"),
                },
              }),
              { data: body, etag: null },
            );
          }
        });
        await screen.findByTestId("outcome-count-documents");
        for (const [key, body] of Object.entries(set.elements)) {
          await act(async () => {
            await navigate(
              `${pathOf(ref)}?${overrides ? `${overrides}&` : ""}selected=${encodeURIComponent(key)}`,
            );
          });
          await waitFor(() => {
            expect(screen.getByTestId("outcome-selected")).toHaveTextContent(
              key.slice(key.indexOf(":") + 1),
            );
            expect(screen.getByTestId("outcome-why-state")).toBeInTheDocument();
          });
          const label = `${set.set} ${key}`;
          if (body.chain.length === 0) {
            expect(
              screen.getByTestId("outcome-chain-empty"),
              label,
            ).toBeInTheDocument();
          } else {
            expect(chainItems(), label).toHaveLength(body.chain.length);
            body.chain.forEach((trace, i) => {
              const li = chainItems()[i]!;
              expect(li, label).toHaveAttribute("data-status", trace.status);
              expect(li, label).toHaveTextContent(
                {
                  held: "Выполнено",
                  not_held: "Не выполнено",
                  skipped: "Не проверялось",
                }[trace.status],
              );
              if (trace.rule.origin === "builtin") {
                expect(li, label).toHaveTextContent("в движке");
              } else {
                expect(li, label).toHaveTextContent(trace.rule.file ?? "");
              }
            });
          }
          if (body.counterfactuals.length > 0) {
            expect(
              within(screen.getByTestId("outcome-whatif")).getAllByRole(
                "button",
              ),
              label,
            ).toHaveLength(body.counterfactuals.length);
          } else {
            expect(
              screen.getByTestId("outcome-whatif-none"),
              label,
            ).toBeInTheDocument();
          }
          if (body.readers.length > 0) {
            expect(
              screen.getByTestId("outcome-readers"),
              label,
            ).toBeInTheDocument();
          }
        }
        client.clear();
        cleanup();
      }
    }, 60_000);
  });

  describe("состояния", () => {
    it("первая загрузка: скелет и aria-busy, затем цепочка и объявление", async () => {
      mount("selected=documents:operator_manual");
      expect(
        await screen.findByTestId("outcome-why-loading"),
      ).toBeInTheDocument();
      expect(screen.getByTestId("outcome-why")).toHaveAttribute(
        "aria-busy",
        "true",
      );
      await screen.findByTestId("outcome-chain");
      await waitFor(() => {
        expect(screen.getByTestId("outcome-why-live")).toHaveTextContent(
          "Причина загружена: Руководство оператора",
        );
      });
      expect(screen.getByTestId("outcome-why")).toHaveAttribute(
        "aria-busy",
        "false",
      );
    });

    it("пересчёт: прежний ответ того же элемента остаётся, с отметкой", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      await act(async () => {
        await navigate(
          `${pathOf(VKR)}?selected=documents:operator_manual&i.kind=research`,
        );
      });
      expect(screen.getByTestId("outcome-chain")).toBeInTheDocument();
      expect(screen.getByTestId("outcome-why")).toHaveAttribute(
        "data-stale",
        "true",
      );
      expect(screen.getByTestId("outcome-why-refreshing")).toHaveTextContent(
        "Считаю",
      );
      await waitFor(() => {
        expect(screen.getByTestId("outcome-why")).not.toHaveAttribute(
          "data-stale",
        );
      });
    });

    it("другой элемент: чужая цепочка под новым заголовком не показывается", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      await act(async () => {
        await navigate(`${pathOf(VKR)}?selected=participants:co_supervisor`);
      });
      expect(screen.queryByTestId("outcome-chain")).toBeNull();
      await screen.findByTestId("outcome-chain-empty");
    });

    it("404: элемент исчез, выбор снят, результат обновлён молча", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      setExplainBehavior("gone");
      await act(async () => {
        await navigate(`${pathOf(VKR)}?selected=documents:thesis`);
      });
      await waitFor(() => {
        expect(location()).not.toContain("selected=");
      });
      expect(screen.getByTestId("outcome-rules-empty")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("503 outcome_busy: повтор через retry_after_s и ответ без ошибки", async () => {
      setExplainBehavior("busy");
      mount("selected=documents:thesis");
      await screen.findByTestId("outcome-chain");
      expect(screen.queryByTestId("outcome-why-error")).toBeNull();
    });

    it("сбой сервера: плашка, «Повторить» загружает причину", async () => {
      setExplainBehavior("fail");
      mount("selected=documents:thesis");
      const error = await screen.findByTestId("outcome-why-error", undefined, {
        timeout: 4000,
      });
      expect(error).toHaveTextContent("Не удалось загрузить причину");
      expect(screen.getByTestId("outcome-why-live")).toHaveTextContent(
        "Причину загрузить не удалось",
      );
      setExplainBehavior("normal");
      fireEvent.click(screen.getByTestId("outcome-why-retry"));
      await screen.findByTestId("outcome-chain");
      expect(screen.queryByTestId("outcome-why-error")).toBeNull();
    }, 10_000);

    it("ничего не выбрано: подсказка", async () => {
      mount();
      await screen.findByTestId("outcome-count-documents");
      expect(screen.getByTestId("outcome-rules-empty")).toHaveTextContent(
        "Элемент не выбран",
      );
    });

    it("«Снять выбор» убирает элемент из адреса", async () => {
      mount("selected=documents:thesis");
      await screen.findByTestId("outcome-chain");
      fireEvent.click(screen.getByTestId("outcome-selected-clear"));
      expect(location()).not.toContain("selected=");
    });
  });

  describe("«Что если»", () => {
    it("клик применяет ОДНУ вводную, остальные в адресе не трогаются", async () => {
      mount("selected=documents:operator_manual&i.staffing=team2");
      await screen.findByTestId("outcome-whatif");
      fireEvent.click(screen.getByTestId("outcome-whatif-kind-research"));
      const query = new URLSearchParams(location()?.split("?")[1]);
      expect(query.get("i.kind")).toBe("research");
      expect(query.get("i.staffing")).toBe("team2");
      expect([...query.keys()].filter((k) => k.startsWith("i."))).toHaveLength(
        2,
      );
      expect(query.get("selected")).toBe("documents:operator_manual");
      expect(
        await screen.findByTestId("outcome-whatif-applied"),
      ).toHaveTextContent("Применено: «вид работы»: исследовательский");
    });

    it("«Вернуть» возвращает прежнее значение и убирает запись", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-whatif");
      fireEvent.click(screen.getByTestId("outcome-whatif-kind-research"));
      expect(location()).toContain("i.kind=research");
      fireEvent.click(await screen.findByTestId("outcome-whatif-restore"));
      expect(location()).not.toContain("i.kind");
      await waitFor(() => {
        expect(screen.queryByTestId("outcome-whatif-applied")).toBeNull();
      });
    });

    it("«Вернуть» ставит значение, которое было в адресе", async () => {
      mount("selected=documents:operator_manual&i.kind=project");
      await screen.findByTestId("outcome-whatif");
      fireEvent.click(screen.getByTestId("outcome-whatif-kind-research"));
      expect(location()).toContain("i.kind=research");
      fireEvent.click(await screen.findByTestId("outcome-whatif-restore"));
      expect(location()).toContain("i.kind=project");
    });
  });

  describe("переход к правилу", () => {
    const decode = () => {
      const [path, query] = (location() ?? "").split("?");
      return { path, params: new URLSearchParams(query) };
    };

    it("«Открыть правило» ведёт на файл версии, указатель и вкладку «Форма»", async () => {
      mount("selected=documents:operator_manual&i.staffing=team2");
      await screen.findByTestId("outcome-chain");
      fireEvent.click(screen.getByTestId("outcome-chain-t22-open"));
      const { path, params } = decode();
      expect(path).toBe(`/pack-studio/w/${WS}`);
      expect(params.get("file")).toBe(
        "hse-cs-se/templates/vkr/versions/2026.1.2/files/operator_manual/doc.yaml",
      );
      expect(params.get("at")).toBe("/supported_kinds");
      expect(params.get("pane")).toBe("form");
      // Возврат сохраняет вводные и выбранный элемент.
      const from = params.get("from") ?? "";
      expect(from.startsWith(pathOf(VKR))).toBe(true);
      const back = new URLSearchParams(from.split("?")[1]);
      expect(back.get("selected")).toBe("documents:operator_manual");
      expect(back.get("i.staffing")).toBe("team2");
    });

    it("«Исходник» открывает ту же запись вкладкой «Исходник»", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      fireEvent.click(screen.getByTestId("outcome-chain-t22-source"));
      expect(decode().params.get("pane")).toBe("source");
      expect(decode().params.get("at")).toBe("/supported_kinds");
    });

    it("правило version.yaml: указатель слота подписи", async () => {
      mount(
        "selected=route:topic-approval/topic_application/co_supervisor&i.supervisor=university&i.co_supervisor=no&i.academic_supervisor=yes",
        COURSEWORK,
      );
      await screen.findByTestId("outcome-chain");
      fireEvent.click(screen.getByTestId("outcome-chain-t14-open"));
      const { params } = decode();
      expect(params.get("file")).toBe(
        "hse-cs-sse/templates/coursework/versions/2026.1.6/version.yaml",
      );
      expect(params.get("at")).toBe(
        "/pack_submission/profiles/0/signing_slots/0/when",
      );
    });
  });

  describe("клавиатура и доступность", () => {
    it("цепочка это нумерованный список с подписью, у пункта слово-исход", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      const list = screen.getByRole("list", { name: "Цепочка правил" });
      expect(list.tagName).toBe("OL");
      for (const li of within(list).getAllByRole("listitem")) {
        expect(li.textContent).toMatch(/Выполнено|Не выполнено|Не проверялось/);
      }
    });

    it("Tab доходит до «Открыть правило», Enter выполняет, Space применяет «что если»", async () => {
      const user = userEvent.setup();
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      const open = screen.getByTestId("outcome-chain-t22-open");
      open.focus();
      await user.tab();
      expect(screen.getByTestId("outcome-chain-t22-source")).toHaveFocus();
      const whatIf = screen.getByTestId("outcome-whatif-kind-research");
      whatIf.focus();
      await user.keyboard(" ");
      expect(location()).toContain("i.kind=research");
      open.focus();
      await user.keyboard("{Enter}");
      expect(location()).toContain("pane=form");
    });

    it("F6 переводит фокус в панель, у панели есть имя", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      const panel = screen.getByTestId("outcome-rules-panel");
      expect(panel).toHaveAccessibleName("Правила и причины");
      const result = screen.getByTestId("outcome-center");
      result.focus();
      fireEvent.keyDown(result, { key: "F6" });
      expect(panel).toHaveFocus();
    });

    it("Alt+Z открывает свёрнутую панель и переводит в неё фокус", async () => {
      window.localStorage.setItem("hse-studio.packOutcome.right.off", "1");
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-rail-why");
      expect(screen.queryByTestId("outcome-rules-panel")).toBeNull();
      fireEvent.keyDown(screen.getByTestId("outcome-screen"), {
        key: "z",
        code: "KeyZ",
        altKey: true,
      });
      const panel = await screen.findByTestId("outcome-rules-panel");
      await waitFor(() => {
        expect(panel).toHaveFocus();
      });
    });

    it("Alt+Z из панели прячет её, фокус остаётся на экране и возвращает панель", async () => {
      mount("selected=documents:operator_manual");
      await screen.findByTestId("outcome-chain");
      const panel = screen.getByTestId("outcome-rules-panel");
      panel.focus();
      const press = () =>
        fireEvent.keyDown(document.activeElement ?? document.body, {
          key: "z",
          code: "KeyZ",
          altKey: true,
        });
      press();
      await waitFor(() => {
        expect(screen.queryByTestId("outcome-rules-panel")).toBeNull();
      });
      expect(screen.getByTestId("outcome-center")).toHaveFocus();
      press();
      expect(await screen.findByTestId("outcome-rules-panel")).toHaveFocus();
    });

    it("сосед из списка выбирается Enter с клавиатуры", async () => {
      const user = userEvent.setup();
      mount("selected=route:checkpoint-1");
      await screen.findByTestId("outcome-readers");
      const first = within(screen.getByTestId("outcome-readers")).getAllByRole(
        "button",
      )[0]!;
      first.focus();
      await user.keyboard("{Enter}");
      expect(location()).not.toContain("selected=route%3Acheckpoint-1");
    });
  });

  describe("влияние вводной", () => {
    it("у вводной: сколько элементов в скольких разделах и сколько правил читают", async () => {
      mount("selected=branches:kind");
      const summary = await screen.findByTestId("outcome-impact-summary");
      expect(summary.textContent).toMatch(
        /^Влияет на \d+ элемент\S*, в \d+ раздел\S*, читают правил: \d+$/,
      );
      expect(screen.getByTestId("outcome-why-title")).toHaveTextContent(
        "Вид работы",
      );
      expect(
        screen.getByTestId("outcome-impact-documents"),
      ).toBeInTheDocument();
    });

    it("клик по элементу из списка выбирает его и открывает «Почему?»", async () => {
      mount("selected=branches:kind");
      const section = await screen.findByTestId("outcome-impact-documents");
      fireEvent.click(within(section).getAllByRole("button")[0]!);
      expect(location()).toContain("selected=documents");
      await screen.findByTestId("outcome-chain");
    });

    it("список правил: файл, указатель и «Открыть правило»", async () => {
      mount("selected=branches:kind");
      const rules = await screen.findByTestId("outcome-impact-rules");
      expect(rules).toHaveTextContent("/supported_kinds");
      fireEvent.click(
        within(rules).getAllByRole("button", {
          name: /Открыть правило/,
        })[0]!,
      );
      expect(location()).toContain("pane=form");
    });

    it("вводная без влияния: спокойный текст", async () => {
      mount("selected=branches:variant.presentation");
      await screen.findByTestId("outcome-why-title");
      await waitFor(() => {
        expect(
          screen.queryByTestId("outcome-impact-wait"),
        ).not.toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("outcome-impact-inert") ??
          screen.getByTestId("outcome-impact-summary"),
      ).toBeInTheDocument();
    });

    it("неизвестная вводная в адресе не ломает панель", async () => {
      mount("selected=branches:nope.nothing");
      expect(
        await screen.findByTestId("outcome-impact-unknown"),
      ).toBeInTheDocument();
    });

    it("«Влияние» в панели вводных выбирает вводную", async () => {
      mount();
      const btn = await screen.findByTestId("outcome-input-kind-impact");
      fireEvent.click(btn);
      expect(location()).toContain("selected=branches%3Akind");
      await screen.findByTestId("outcome-impact");
      expect(btn).toHaveAttribute("aria-pressed", "true");
    });
  });

  describe("языки", () => {
    it("английский словарь: цепочка, состояния, что если", async () => {
      await i18n.changeLanguage("en");
      try {
        mount("selected=documents:operator_manual");
        await screen.findByTestId("outcome-chain");
        expect(
          screen.getByRole("list", { name: "Rule chain" }),
        ).toBeInTheDocument();
        expect(screen.getByTestId("outcome-why-state")).toHaveTextContent(
          "switched off",
        );
        const items = chainItems();
        expect(items[2]).toHaveTextContent("Not held");
        expect(items[2]).toHaveTextContent("in the engine");
        expect(screen.getByTestId("outcome-chain-t22-open")).toHaveTextContent(
          "Open rule",
        );
        expect(screen.getByTestId("outcome-whatif")).toHaveTextContent(
          "What changes if...",
        );
        expect(screen.getByTestId("outcome-why-live")).toHaveTextContent(
          "Reason loaded",
        );
        // Ни одного ключа словаря вместо текста.
        expect(screen.getByTestId("outcome-rules").textContent).not.toMatch(
          /\b(rules|reasons|status|sections)\.[a-z]/,
        );
      } finally {
        await i18n.changeLanguage("ru");
      }
    });

    it("английский: влияние вводной", async () => {
      await i18n.changeLanguage("en");
      try {
        mount("selected=branches:kind");
        const summary = await screen.findByTestId("outcome-impact-summary");
        expect(summary.textContent).toMatch(
          /^Affects \d+ elements?, in \d+ sections?, read by \d+ rules$/,
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

    it("«Почему?» страницей работает, переход к файлам скрыт", async () => {
      mount("tab=rules&selected=documents:operator_manual");
      const sheet = await screen.findByTestId("outcome-rules-page");
      await within(sheet).findByTestId("outcome-chain");
      expect(within(sheet).queryByTestId("outcome-chain-t22-open")).toBeNull();
      expect(within(sheet).getByTestId("outcome-whatif")).toBeInTheDocument();
      expect(sheet).toHaveTextContent("Правка доступна на компьютере");
    });
  });
});
