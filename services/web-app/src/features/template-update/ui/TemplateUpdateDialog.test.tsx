import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AvailableUpdate,
  TemplateFileOp,
  TemplateUpdatePlan,
} from "@entities/template-update";

// The `@shared/ui` barrel eagerly loads pdfjs-dist, which needs DOMMatrix.
vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve(null) }),
  version: "0",
}));

const applyMutate = vi.fn();
const refetch = vi.fn();
const diffCalls: { path: string; view: string }[] = [];
let plan: TemplateUpdatePlan;

vi.mock("@entities/template-update", () => ({
  useTemplateUpdatePlan: () => ({
    data: plan,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch,
  }),
  useApplyTemplateUpdate: () => ({ mutate: applyMutate, isPending: false }),
  useTemplateFileDiff: (
    _projectId: string,
    params: { path: string; view: string },
  ) => {
    diffCalls.push({ path: params.path, view: params.view });
    return {
      data: {
        path: params.path,
        binary: false,
        truncated: false,
        patch: "@@ -1,2 +1,2 @@\n keep\n-old line\n+new line\n",
      },
      isLoading: false,
      isError: false,
    };
  },
}));

import {
  SR_DOC,
  SR_PROJECT_ID,
  SR_REVIEW_DOC,
  makeSigningRouteSummary,
} from "@entities/signing-route/testing";
import { guardKey } from "@entities/signing-route";
import {
  GUARD_DOCS,
  makeGuardHarness,
} from "@entities/signing-route/testing/guard";
import { TemplateUpdateDialog } from "./TemplateUpdateDialog";

const op = (
  path: string,
  action: string,
  extra: Partial<TemplateFileOp> = {},
): TemplateFileOp => ({
  path,
  action,
  binary: false,
  doc_id: null,
  conflicts: 0,
  approximate_base: false,
  resolutions: [],
  ...extra,
});

const update: AvailableUpdate = {
  version: {
    version: "2.1.0",
    status: "released",
    released_at: "2026-01-01",
    summary: {},
    changes: { ru: ["Новая титульная страница"], en: ["New title page"] },
    breaking_changes: {},
    released: true,
  },
  update_class: "minor",
};

const makePlan = (): TemplateUpdatePlan => ({
  from_version: "2.0.0",
  to_version: "2.1.0",
  update_class: "minor",
  provenance: "approximate",
  fingerprint: "fp-1",
  counts: { conflict: 1, merge: 1, update: 2, add: 1 },
  files: [
    op("z/title.tex", "update"),
    op("a/new.tex", "add"),
    op("b/main.tex", "conflict", {
      conflicts: 2,
      resolutions: ["mine", "theirs", "markers"],
    }),
    op("c/merge.tex", "merge", { approximate_base: true }),
    op("a/style.sty", "update"),
  ],
  warnings: [{ code: "frozen_documents", doc_ids: ["report"] }],
});

const renderDialog = () => {
  const onClose = vi.fn();
  render(
    <TemplateUpdateDialog projectId="p1" update={update} onClose={onClose} />,
  );
  return { onClose };
};

describe("TemplateUpdateDialog (list rendering)", () => {
  beforeEach(() => {
    cleanup();
    applyMutate.mockReset();
    refetch.mockReset();
    diffCalls.length = 0;
    plan = makePlan();
  });

  it("shows the title, notes, warnings and the provenance notice", () => {
    renderDialog();
    expect(
      screen.getByRole("dialog", { name: /2\.0\.0.*2\.1\.0/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Новая титульная страница")).toBeInTheDocument();
    expect(
      screen.getByText(/Истории создания проекта нет/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/зафиксированные на подпись.*report/),
    ).toBeInTheDocument();
  });

  it("an empty file plan with template signature places is not «nothing to update»", () => {
    plan = {
      ...makePlan(),
      counts: {},
      files: [],
      warnings: [],
      signature_presets: {
        updated: [
          { doc_id: "report", slot_id: "supervisor" },
          { doc_id: "report", slot_id: "author" },
        ],
        kept: [{ doc_id: "proposal", slot_id: "supervisor", reason: "route" }],
      },
    };
    renderDialog();
    expect(
      screen.getByText(
        "Файлы не меняются. Обновятся места подписей из шаблона: 2",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/не меняет ни одного файла/)).toBeNull();
  });

  it("an empty file plan without signature places says the version still applies", () => {
    plan = { ...makePlan(), counts: {}, files: [], warnings: [] };
    renderDialog();
    expect(screen.getByText(/не меняет ни одного файла/)).toBeInTheDocument();
  });

  it("lists files with decisions first and a tag per action", () => {
    renderDialog();
    const rows = screen
      .getAllByTitle(/\.(tex|sty)$/)
      .map((el) => el.getAttribute("title"));
    expect(rows).toEqual([
      "b/main.tex",
      "c/merge.tex",
      "a/style.sty",
      "z/title.tex",
      "a/new.tex",
    ]);
    const conflictRow = screen.getByTitle("b/main.tex").closest("button");
    expect(conflictRow).not.toBeNull();
    expect(
      within(conflictRow as HTMLElement).getByText("конфликт"),
    ).toBeVisible();
    expect(screen.getByText("слияние")).toBeVisible();
    expect(screen.getByText("новый")).toBeVisible();
  });

  it("renders count badges with the action tone colour", () => {
    renderDialog();
    const badge = screen.getByText("1 · конфликты");
    expect(badge).toHaveClass("badge");
    expect(badge.style.color).toBe("var(--c-err)");
    expect(screen.getByText("2 · обновятся").style.color).toBe("var(--fg-2)");
    expect(screen.getByText("1 · новые").style.color).toBe("var(--c-ok)");
  });

  it("offers a resolution select only for conflicts, defaulting to mine", () => {
    renderDialog();
    const selects = screen.getAllByRole("combobox");
    expect(selects).toHaveLength(1);
    expect(selects[0]).toHaveTextContent("Оставить моё");
  });

  it("shows a placeholder until a file is selected, then the view tabs and diff", async () => {
    const user = userEvent.setup();
    renderDialog();
    expect(
      screen.getByText("Выберите файл, чтобы увидеть изменения"),
    ).toBeInTheDocument();
    await user.click(screen.getByTitle("b/main.tex"));
    expect(
      screen.getByRole("button", { name: "Что меняет шаблон" }),
    ).toHaveClass("primary");
    expect(screen.getByRole("button", { name: "Мои правки" })).not.toHaveClass(
      "primary",
    );
    expect(screen.getByText("new line")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Что получится" }));
    expect(diffCalls.at(-1)).toEqual({ path: "b/main.tex", view: "result" });
  });

  it("limits the tabs for files that exist on one side only", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByTitle("a/new.tex"));
    expect(
      screen.getAllByRole("button", { name: /Что меняет шаблон|Мои правки/ }),
    ).toHaveLength(1);
  });

  it("applies exactly the plan that is shown, with the conflict decisions", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(applyMutate).toHaveBeenCalledTimes(1);
    expect(applyMutate.mock.calls[0]?.[0]).toEqual({
      projectId: "p1",
      params: {
        to_version: "2.1.0",
        fingerprint: "fp-1",
        resolutions: { "b/main.tex": "mine" },
      },
    });
  });
});

describe("TemplateUpdateDialog (documents out for signing)", () => {
  beforeEach(() => {
    cleanup();
    applyMutate.mockReset();
    plan = makePlan();
  });

  const renderHeld = (files: TemplateFileOp[]) => {
    plan = { ...makePlan(), files };
    const route = makeSigningRouteSummary({
      docs: [SR_DOC.doc_id, SR_REVIEW_DOC.doc_id],
    });
    // Третий документ проекта не на подписании: его файлы никого не задевают.
    const harness = makeGuardHarness({
      routes: [route],
      docs: [...GUARD_DOCS, { id: "other", name: "Другой", folder: "other" }],
    });
    render(
      <TemplateUpdateDialog
        projectId={SR_PROJECT_ID}
        update={update}
        onClose={vi.fn()}
      />,
      { wrapper: harness.wrapper },
    );
    return { harness, route };
  };

  it("names the held documents the plan touches in one line, without a separate window", async () => {
    const user = userEvent.setup();
    const { harness, route } = renderHeld([
      op(`${SR_DOC.doc_id}/title.tex`, "update"),
      op("other/x.tex", "update"),
    ]);
    expect(
      screen.getByText(
        "Документ на подписании: Заявление о выборе темы. Обновление не попадёт в подписываемую версию: после обновления маршрут попросит отправить новую версию (кнопка «Отправить новую версию» в карточке «Подписание»).",
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Обновить/ }));
    expect(applyMutate).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    // Строку видели: правка этого документа потом уже не спрашивает.
    expect(
      harness.memory.has(
        guardKey(SR_PROJECT_ID, {
          docId: SR_DOC.doc_id,
          routeId: route.id,
          round: route.round,
        }),
      ),
    ).toBe(true);
  });

  it("lists every held document when shared files change", () => {
    renderHeld([op("common/preamble.tex", "update")]);
    expect(
      screen.getByText(
        "Документы на подписании: Заявление о выборе темы, Отзыв руководителя. Обновление не попадёт в подписываемые версии: после обновления маршрут попросит отправить новую версию (кнопка «Отправить новую версию» в карточке «Подписание»).",
      ),
    ).toBeInTheDocument();
  });

  it("says nothing when the plan touches no held document", () => {
    renderHeld([op("other/x.tex", "update")]);
    expect(screen.queryByText(/на подписании/)).toBeNull();
  });
});
