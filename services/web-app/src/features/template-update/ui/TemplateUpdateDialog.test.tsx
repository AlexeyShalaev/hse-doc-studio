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
    expect(badge).toHaveStyle({ color: "var(--c-err)" });
    expect(screen.getByText("2 · обновятся")).toHaveStyle({
      color: "var(--fg-2)",
    });
    expect(screen.getByText("1 · новые")).toHaveStyle({
      color: "var(--c-ok)",
    });
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
