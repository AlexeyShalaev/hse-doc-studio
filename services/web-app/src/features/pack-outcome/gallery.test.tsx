import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { getPackOutcomeGallery } from "./gallery";

describe("галерея экрана «Результат»", () => {
  beforeAll(async () => {
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
  });
  afterEach(cleanup);

  const entries = getPackOutcomeGallery().flatMap((g) => g.entries);

  it("id записей уникальны, записей хватает на все состояния", () => {
    const ids = entries.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(
      expect.arrayContaining([
        "po_result",
        "po_loading",
        "po_unreadable",
        "po_empty",
        "po_sections_points",
        "po_sections_route",
        "po_inputs_vkr",
        "po_inputs_changed",
        "po_inputs_scenario",
        "po_inputs_coursework",
        "po_inputs_error",
        "po_scenarios_picker",
        "po_scenarios_empty",
        "po_scenarios_broken",
        "po_scenarios_running",
        "po_scenario_create",
        "po_scenario_panel_failed",
        "po_scenario_panel_broken",
        "po_scenario_save_inputs",
        "po_inputs_none",
        "po_checks",
        "po_checks_error",
        "po_branches",
        "po_branches_error",
        "po_why_document_off",
        "po_why_document_on",
        "po_why_field_hidden",
        "po_why_empty_chain",
        "po_why_participant_absent",
        "po_why_route_step",
        "po_why_route_skipped",
        "po_why_loading",
        "po_why_error",
        "po_why_busy",
        "po_why_impact",
        "po_mode_matrix",
        "po_mode_matrix_error_row",
        "po_mode_matrix_empty",
        "po_mode_atlas",
        "po_mode_atlas_vkr",
        "po_mode_atlas_too_large",
        "po_mode_compare",
        "po_mode_compare_identical",
        "po_mode_compare_no_base",
        "po_student",
        "po_student_no_supervisor",
        "po_student_team",
        "po_pale_slots",
        "po_edit_ready",
        "po_edit_released",
      ]),
    );
  });

  it.each(["ru", "en"])(
    "записи рисуются без сервера (%s)",
    async (lng) => {
      await i18n.changeLanguage(lng);
      for (const entry of entries) {
        const client = new QueryClient({
          defaultOptions: { queries: { retry: false, staleTime: Infinity } },
        });
        entry.seed?.(client);
        const { container, unmount } = render(
          <QueryClientProvider client={client}>
            <MemoryRouter>{entry.render()}</MemoryRouter>
          </QueryClientProvider>,
        );
        expect(container.textContent.length, entry.id).toBeGreaterThan(0);
        // Ни одного ключа словаря вместо текста.
        expect(container.textContent, entry.id).not.toMatch(
          /\b(bar|status|panels|inputs|result|sections|rules|footer|errors|points|route|reasons)\.[a-z]/,
        );
        unmount();
      }
      await i18n.changeLanguage("ru");
      // Записей много, а CI медленнее машины разработчика: общий предел вместо 5 с.
    },
    60_000,
  );

  it("запись с адресом показывает состояние из query", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_state_in_url");
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      container.querySelector('[data-testid="outcome-selected"]')?.textContent,
    ).toContain("operator_manual");
    expect(
      container
        .querySelector('[data-testid="outcome-control-kind-research"]')
        ?.getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("запись «Вводные: изменены» подсвечивает три вводные", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_inputs_changed");
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(3);
  });

  it("запись «курсовой проект» строит панель из вводных курсового", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_inputs_coursework");
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    // Поля курсового трасса не читает: они в блоке «Не влияют» (он свёрнут).
    const toggle = container.querySelector(
      '[data-testid="outcome-inputs-inert-toggle"]',
    );
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    if (!toggle) throw new Error("inert toggle is missing");
    fireEvent.click(toggle);
    expect(
      container.querySelector(
        '[data-testid="outcome-input-meta.proposal_stage"]',
      ),
    ).not.toBeNull();
    expect(
      container
        .querySelector('[data-testid="outcome-control-supervisor-company"]')
        ?.getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("запись маршрута рисует параллельный шаг и пропущенную пару", async () => {
    await i18n.changeLanguage("ru");
    const entry = entries.find((e) => e.id === "po_sections_route");
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    const lane = container.querySelector(
      '[data-testid="outcome-route-pdp-application-steps"]',
    );
    expect(lane?.tagName).toBe("OL");
    expect(lane?.querySelectorAll("li")).toHaveLength(2);
    expect(
      container.querySelector('[data-testid="outcome-step-pdp-application-2"]')
        ?.textContent,
    ).toContain("параллельно");
    expect(
      container.querySelector(
        '[data-testid="outcome-route-pdp-application-skipped"]',
      ),
    ).not.toBeNull();
  });

  it.each([
    ["po_checks", "outcome-check-gost-7.32-2017/line-spacing"],
    ["po_branches", "outcome-branch-staffing"],
  ])(
    "запись %s показывает раскрытый раздел с данными из кэша",
    (id, testId) => {
      const entry = entries.find((e) => e.id === id);
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      entry?.seed?.(client);
      const { container } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter>{entry?.render()}</MemoryRouter>
        </QueryClientProvider>,
      );
      expect(
        container.querySelector(`[data-testid="${testId}"]`),
      ).not.toBeNull();
    },
  );

  it.each(["po_checks_error", "po_branches_error"])(
    "запись %s показывает сбой запроса части",
    (id) => {
      const entry = entries.find((e) => e.id === id);
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: Infinity } },
      });
      entry?.seed?.(client);
      const { container } = render(
        <QueryClientProvider client={client}>
          <MemoryRouter>{entry?.render()}</MemoryRouter>
        </QueryClientProvider>,
      );
      expect(container.querySelector('[role="alert"]')).not.toBeNull();
    },
  );
});

describe("галерея «Почему?»", () => {
  beforeAll(async () => {
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  const show = (id: string) => {
    const entry = getPackOutcomeGallery()
      .flatMap((g) => g.entries)
      .find((e) => e.id === id);
    expect(entry, id).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it("документ выключен: цепочка и «что если» из кэша, без сервера", () => {
    const { container } = show("po_why_document_off");
    expect(
      container.querySelector('[data-testid="outcome-chain"]'),
    ).not.toBeNull();
    expect(
      container.querySelectorAll('[data-testid="outcome-chain"] > li'),
    ).toHaveLength(4);
    expect(
      container.querySelector('[data-testid="outcome-whatif"]'),
    ).not.toBeNull();
  });

  it("загрузка, сбой и занятый сервер рисуют своё состояние", () => {
    expect(
      show("po_why_loading").container.querySelector(
        '[data-testid="outcome-why-loading"]',
      ),
    ).not.toBeNull();
    cleanup();
    expect(
      show("po_why_error").container.querySelector(
        '[data-testid="outcome-why-error"]',
      ),
    ).not.toBeNull();
    cleanup();
    expect(
      show("po_why_busy").container.querySelector(
        '[data-testid="outcome-why-error"]',
      )?.textContent,
    ).toContain("Сервер занят");
  });

  it("влияние вводной и пустая цепочка", () => {
    expect(
      show("po_why_impact").container.querySelector(
        '[data-testid="outcome-impact-summary"]',
      ),
    ).not.toBeNull();
    cleanup();
    expect(
      show("po_why_empty_chain").container.querySelector(
        '[data-testid="outcome-chain-empty"]',
      ),
    ).not.toBeNull();
  });

  it.each([
    ["po_mode_matrix", "outcome-matrix-cell-company-supervisor-route"],
    ["po_mode_matrix_error_row", "outcome-matrix-message-company-supervisor"],
    ["po_mode_matrix_empty", "outcome-matrix-empty"],
    ["po_mode_matrix_too_large", "outcome-mode-too-large"],
    ["po_mode_matrix_loading", "outcome-matrix-loading"],
    ["po_mode_atlas", "outcome-atlas-detail"],
    ["po_mode_atlas_vkr", "outcome-atlas-more"],
    ["po_mode_atlas_pinned", "outcome-atlas-pins"],
    ["po_mode_atlas_loading", "outcome-atlas-cancel"],
    ["po_mode_atlas_busy", "outcome-mode-busy"],
    ["po_mode_atlas_too_large", "outcome-atlas-pinchoose"],
    ["po_mode_compare", "outcome-compare-section-route"],
    ["po_mode_compare_identical", "outcome-compare-identical"],
    ["po_mode_compare_no_base", "outcome-mode-no-base"],
    ["po_mode_compare_loading", "outcome-compare-loading"],
  ])("режим «%s» рисуется из кэша без сервера", async (id, testId) => {
    await i18n.changeLanguage("ru");
    const entry = getPackOutcomeGallery()
      .flatMap((g) => g.entries)
      .find((e) => e.id === id);
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId(testId)).toBeInTheDocument();
  });
});

describe("галерея режима «Как студент» и бледных слотов", () => {
  beforeAll(async () => {
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  const entries = getPackOutcomeGallery().flatMap((g) => g.entries);
  const draw = (id: string) => {
    const entry = entries.find((e) => e.id === id);
    expect(entry).toBeDefined();
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    entry?.seed?.(client);
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{entry?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
  };
  const find = (root: HTMLElement, testId: string) =>
    root.querySelector(`[data-testid="${testId}"]`);

  it("po_student: три блока, секций автора и правил нет", () => {
    const { container } = draw("po_student");
    expect(find(container, "outcome-student")).not.toBeNull();
    expect(find(container, "outcome-student-route")).not.toBeNull();
    expect(find(container, "outcome-section-documents")).toBeNull();
    expect(find(container, "outcome-rules-panel")).toBeNull();
  });

  it("po_student_no_supervisor: шага отсутствующего руководителя нет", () => {
    const { container } = draw("po_student_no_supervisor");
    expect(
      find(container, "outcome-student-step-pdp-application-1"),
    ).not.toBeNull();
    expect(
      find(container, "outcome-student-step-pdp-application-2"),
    ).toBeNull();
    expect(container.querySelector(".po-person-warn")).toBeNull();
  });

  it("po_student_team: параллельный шаг помечен словами", () => {
    const { container } = draw("po_student_team");
    expect(
      find(container, "outcome-student-step-pdp-application-2")?.textContent,
    ).toContain("параллельно");
  });

  it("po_pale_slots: бледный участник и «Добавить во вводных» на месте", () => {
    const { container } = draw("po_pale_slots");
    expect(
      find(container, "outcome-participant-co_supervisor")?.getAttribute(
        "data-pale",
      ),
    ).toBe("true");
    expect(
      find(container, "outcome-pale-add-participants-co_supervisor"),
    ).not.toBeNull();
  });
});

describe("галерея: правка по месту", () => {
  beforeAll(async () => {
    await Promise.all([loadPackOutcomeNamespace(), loadPackStudioNamespace()]);
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);
  const entry = (id: string) =>
    getPackOutcomeGallery()
      .flatMap((g) => g.entries)
      .find((e) => e.id === id);
  const show = (id: string) => {
    const found = entry(id);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    found?.seed?.(client);
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>{found?.render()}</MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it("рабочее дерево: «Править правило» доступна", async () => {
    const { findByTestId } = show("po_edit_ready");
    expect(await findByTestId("outcome-chain-t14-edit")).toBeEnabled();
  });

  it("выпущенная версия: кнопка неактивна, есть объяснение и ссылка на новую версию", async () => {
    const { findByTestId } = show("po_edit_released");
    expect(await findByTestId("outcome-chain-t1-edit")).toBeDisabled();
    expect(await findByTestId("outcome-chain-t1-new-version")).toHaveAttribute(
      "href",
      expect.stringContaining("newVersion=hse-cs-se%2Fvkr"),
    );
  });
});
