import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConflictFile, FileResolution } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import { DeleteModifyResolver } from "./DeleteModifyResolver";

const present = {
  exists: true,
  size: 2_048,
  author: "Иван Смирнов",
  at: "2026-10-26T10:00:00Z",
};
const gone = { exists: false, size: null, author: "Анна Петрова", at: null };

const deletedByThem: ConflictFile = {
  path: "chapters/appendix.tex",
  owner: null,
  kind: "text",
  action: "conflict",
  conflict_type: "deleted_by_them",
  hunks: 0,
  open_hunks: 0,
  fields: 0,
  open_fields: 0,
  resolved: false,
  resolution: null,
  allowed: ["mine", "theirs"],
  default_resolution: null,
  sides: { ours: present, theirs: gone, base: present },
  copy_path: null,
  doc_id: null,
};

const deletedByUs: ConflictFile = {
  ...deletedByThem,
  conflict_type: "deleted_by_us",
  sides: {
    ours: { ...gone, author: "Иван Смирнов" },
    theirs: { ...present, author: "Анна Петрова" },
    base: present,
  },
};

const renderResolver = (
  file: ConflictFile,
  resolution: FileResolution | null = null,
  extra: { deletedBy?: "ours" | "theirs" | null } = {},
) => {
  const onChoose = vi.fn();
  render(
    <DeleteModifyResolver
      file={file}
      resolution={resolution}
      theirsAuthor="Анна Петрова"
      onChoose={onChoose}
      {...extra}
    />,
  );
  return onChoose;
};

describe("DeleteModifyResolver", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterEach(cleanup);

  it("offers to keep the changed file or delete it, when the repository deleted it", async () => {
    const user = userEvent.setup();
    const onChoose = renderResolver(deletedByThem);
    const keep = screen.getByRole("radio", {
      name: /Оставить файл с моими изменениями/,
    });
    const remove = screen.getByRole("radio", {
      name: /Удалить файл, как в репозитории/,
    });
    await user.click(keep);
    expect(onChoose).toHaveBeenLastCalledWith("mine");
    await user.click(remove);
    expect(onChoose).toHaveBeenLastCalledWith("theirs");
  });

  it("spells out the consequence of each option", () => {
    renderResolver(deletedByThem);
    expect(
      screen.getByText(/Файл останется в проекте с твоими правками/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Файл исчезнет из проекта, твои правки в нём не сохранятся/,
      ),
    ).toBeInTheDocument();
  });

  it("names who changed the file and who deleted it", () => {
    renderResolver(deletedByThem);
    expect(screen.getByText(/Изменил: Иван Смирнов/)).toBeInTheDocument();
    expect(screen.getByText("Удалил: Анна Петрова")).toBeInTheDocument();
    expect(screen.getByText(/2 кБ/)).toBeInTheDocument();
  });

  it("flips the options when the file was deleted here and changed there", async () => {
    const user = userEvent.setup();
    const onChoose = renderResolver(deletedByUs);
    expect(
      screen.getByRole("radio", { name: /Оставить файл удалённым/ }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("radio", {
        name: /Вернуть файл с изменениями из репозитория/,
      }),
    );
    expect(onChoose).toHaveBeenLastCalledWith("theirs");
    expect(screen.getByText(/Изменил: Анна Петрова/)).toBeInTheDocument();
    expect(screen.getByText("Удалил: Иван Смирнов")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Файл вернётся в проект вместе с правками из репозитория.",
      ),
    ).toBeInTheDocument();
  });

  it("marks the chosen option", () => {
    renderResolver(deletedByThem, { kind: "file", choice: "theirs" });
    expect(
      screen.getByRole("radio", { name: /Удалить файл, как в репозитории/ }),
    ).toBeChecked();
    expect(
      screen.getByRole("radio", { name: /Оставить файл с моими изменениями/ }),
    ).not.toBeChecked();
  });

  it("takes the deleting side from the details when the type does not say", () => {
    renderResolver({ ...deletedByThem, conflict_type: null }, null, {
      deletedBy: "ours",
    });
    expect(
      screen.getByRole("radio", { name: /Оставить файл удалённым/ }),
    ).toBeInTheDocument();
  });

  it("only shows the options the server allows", () => {
    renderResolver({ ...deletedByThem, allowed: ["mine"] });
    expect(screen.getAllByRole("radio")).toHaveLength(1);
  });

  it("speaks English", async () => {
    await i18n.changeLanguage("en");
    renderResolver(deletedByThem);
    expect(screen.getByText(/Changed by: Иван Смирнов/)).toBeInTheDocument();
    expect(screen.getByText("Deleted by: Анна Петрова")).toBeInTheDocument();
  });
});
