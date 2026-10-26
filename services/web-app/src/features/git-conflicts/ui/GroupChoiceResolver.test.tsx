import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConflictFile } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { isGroupConflict } from "../model/conflictModel";
import { GroupChoiceResolver } from "./GroupChoiceResolver";

const side = {
  exists: true,
  size: 4_096,
  author: "Иван Смирнов",
  at: "2026-10-26T10:00:00Z",
};

const fileOf = (overrides: Partial<ConflictFile>): ConflictFile => ({
  path: ".hse-studio/frozen/coursework.pdf",
  owner: null,
  kind: "binary",
  action: "conflict",
  conflict_type: "signature_group",
  hunks: 0,
  open_hunks: 0,
  fields: 0,
  open_fields: 0,
  resolved: false,
  resolution: null,
  allowed: ["mine", "theirs"],
  default_resolution: null,
  sides: {
    ours: side,
    theirs: { ...side, author: "Анна Петрова" },
    base: side,
  },
  copy_path: null,
  doc_id: "coursework",
  ...overrides,
});

const renderResolver = (file: ConflictFile) => {
  const onChoose = vi.fn();
  render(
    <GroupChoiceResolver
      file={file}
      resolution={null}
      theirsAuthor="Анна Петрова"
      onChoose={onChoose}
    />,
  );
  return onChoose;
};

describe("GroupChoiceResolver", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("recognises the conflicts it is for", () => {
    expect(isGroupConflict(fileOf({}))).toBe(true);
    expect(isGroupConflict(fileOf({ conflict_type: "case_collision" }))).toBe(
      true,
    );
    expect(isGroupConflict(fileOf({ conflict_type: "binary" }))).toBe(false);
    expect(isGroupConflict(fileOf({ conflict_type: null }))).toBe(false);
  });

  it("explains why signatures are taken as a whole and names the document", async () => {
    const user = userEvent.setup();
    const onChoose = renderResolver(fileOf({}));
    expect(screen.getByText("Подписи нельзя смешивать")).toBeInTheDocument();
    expect(screen.getByText(/байт в байт/)).toBeInTheDocument();
    expect(screen.getByText("Документ: coursework")).toBeInTheDocument();
    await user.click(
      screen.getByRole("radio", { name: /Оставить мои подписи/ }),
    );
    expect(onChoose).toHaveBeenLastCalledWith("mine");
    await user.click(
      screen.getByRole("radio", { name: /Взять подписи из репозитория/ }),
    );
    expect(onChoose).toHaveBeenLastCalledWith("theirs");
  });

  it("explains a name that differs only by case", async () => {
    const user = userEvent.setup();
    const onChoose = renderResolver(
      fileOf({
        path: "chapters/Appendix.tex",
        kind: "text",
        conflict_type: "case_collision",
        doc_id: null,
      }),
    );
    expect(
      screen.getByText("Имена различаются только регистром"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Документ:/)).toBeNull();
    await user.click(screen.getByRole("radio", { name: /Оставить мой файл/ }));
    expect(onChoose).toHaveBeenLastCalledWith("mine");
    expect(
      screen.getByRole("radio", { name: /Взять файл из репозитория/ }),
    ).toBeInTheDocument();
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderResolver(fileOf({}));
    expect(screen.getByText("Signatures cannot be mixed")).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Keep my signatures/ }),
    ).toBeInTheDocument();
  });
});
