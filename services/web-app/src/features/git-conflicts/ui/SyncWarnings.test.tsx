import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { OperationWarning } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { SyncWarnings } from "./SyncWarnings";

const renderWarnings = (warnings: OperationWarning[]) =>
  render(<SyncWarnings warnings={warnings} />);

describe("SyncWarnings", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("renders nothing without warnings", () => {
    const { container } = renderWarnings([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("explains a missing template and what happens next", () => {
    renderWarnings([{ code: "template_missing_after_merge", paths: [] }]);
    expect(
      screen.getByText("Шаблона нет в этой версии Студии"),
    ).toBeInTheDocument();
    expect(screen.getByText(/откроется только для чтения/)).toBeInTheDocument();
    expect(screen.getByText(/к ней можно вернуться/)).toBeInTheDocument();
    // Без путей раскрывающегося списка нет.
    expect(screen.queryByText(/Файлы:/)).toBeNull();
  });

  it("tells the signatures are stale", () => {
    renderWarnings([
      { code: "signatures_stale", paths: [".hse-studio/signatures.json"] },
    ]);
    expect(screen.getByText("Подписи устарели")).toBeInTheDocument();
    expect(screen.getByText(/Их придётся собрать заново/)).toBeInTheDocument();
  });

  it("lists the skipped paths on demand", async () => {
    const user = userEvent.setup();
    renderWarnings([
      {
        code: "unsafe_path",
        paths: ["../etc/passwd", "a\\b.tex", ".git/config"],
      },
    ]);
    expect(screen.getByText("Часть файлов пропущена")).toBeInTheDocument();
    const summary = screen.getByText("Файлы: 3");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    await user.click(summary);
    expect(details).toHaveAttribute("open");
    expect(
      within(details as HTMLElement).getAllByRole("listitem"),
    ).toHaveLength(3);
    expect(screen.getByText("../etc/passwd")).toBeInTheDocument();
  });

  it("shows several warnings one after another", () => {
    renderWarnings([
      { code: "signatures_stale", paths: [] },
      { code: "unsafe_path", paths: ["x"] },
      { code: "frozen_documents", paths: [] },
    ]);
    const region = screen.getByRole("region", {
      name: "Предупреждения синхронизации",
    });
    expect(within(region).getAllByRole("status")).toHaveLength(3);
  });

  it("does not stay silent about a code it does not know", () => {
    renderWarnings([{ code: "brand_new_warning", paths: [] }]);
    expect(screen.getByText("Предупреждение")).toBeInTheDocument();
    expect(screen.getByText("Код: brand_new_warning")).toBeInTheDocument();
  });

  it.each([
    "template_missing_after_merge",
    "signatures_stale",
    "unsafe_path",
    "case_collision",
    "frozen_documents",
    "team_foreign_edit",
    "template_missing",
    "lfs_pointers",
  ])("has words for %s in both languages", async (code) => {
    for (const lang of ["ru", "en"]) {
      await i18n.changeLanguage(lang);
      renderWarnings([{ code, paths: [] }]);
      expect(screen.queryByText(`warnings.${code}.title`)).toBeNull();
      cleanup();
    }
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderWarnings([{ code: "signatures_stale", paths: ["a.json", "b.json"] }]);
    expect(screen.getByText("Signatures are out of date")).toBeInTheDocument();
    expect(screen.getByText("Files: 2")).toBeInTheDocument();
  });
});
