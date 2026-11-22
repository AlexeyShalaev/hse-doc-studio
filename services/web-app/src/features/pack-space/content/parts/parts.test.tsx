import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { packStudioKeys, type PackTree } from "@entities/pack-studio";
import type { QueryClient } from "@tanstack/react-query";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { GALLERY_TREE, GALLERY_WORKSPACE } from "../../galleryKit";
import { renderContent } from "../contentTestKit";
import type { ContentPart, ContentPartProps } from "../contract";
import { CONTENT_VERSION_DIR } from "../fixtures";
import FilesPart from "./FilesPart";
import { VersionPart } from "./VersionPart";
import RulesPart from "../extend/part-rules";

// Формы, редактор и окно создания подменены пробами: их содержимое тестируют их срезы, а здесь
// проверяется, что раздел навигации открывает ровно свой раздел формы и что «Все файлы» собраны
// из дерева, файла и создания пака по месту.
vi.mock("../FormPane", () => ({
  FormPane: (props: Record<string, unknown>) => (
    <output data-testid="probe-form">
      {JSON.stringify({
        path: props.path,
        section: props.section ?? null,
        at: props.at ?? null,
      })}
    </output>
  ),
}));
vi.mock("../text/TextEditor", () => ({
  TextEditor: (props: Record<string, unknown>) => (
    <output data-testid="probe-text">
      {JSON.stringify({ path: props.path, readOnly: props.readOnly })}
    </output>
  ),
}));
vi.mock("../../nav/CreateDialog", () => ({
  CreateDialog: (props: { target: unknown }) => (
    <output data-testid="probe-create">{JSON.stringify(props.target)}</output>
  ),
}));

const probe = (id: string) =>
  JSON.parse(screen.getByTestId(id).textContent) as Record<string, unknown>;
const location = () => screen.getByTestId("location").textContent;

const props = (
  part: ContentPart,
  over: Partial<ContentPartProps> = {},
): ContentPartProps => ({
  workspaceId: GALLERY_WORKSPACE.id,
  versionDir: CONTENT_VERSION_DIR,
  part,
  at: null,
  file: null,
  readOnly: false,
  ...over,
});

const withFiles = (paths: string[]): PackTree => ({
  ...GALLERY_TREE,
  files: paths.map((path) => ({
    path,
    is_dir: false,
    size: 10,
    read_only: null,
  })),
});

describe("разделы версии «Содержимого»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  afterEach(cleanup);

  it.each([
    ["documents", "documents"],
    ["fields", "fields"],
    ["forms", "forms"],
    ["deadlines", "submission"],
    ["languages", "languages"],
    ["rules", "checks"],
  ] as const)(
    "раздел %s открывает раздел формы %s без полосы вкладок",
    (part, section) => {
      renderContent(<VersionPart {...props(part)} />, `part=${part}`);
      expect(probe("probe-form")).toEqual({
        path: `${CONTENT_VERSION_DIR}/version.yaml`,
        section,
        at: null,
      });
      expect(screen.getByTestId(`ct-part-${part}`)).toHaveTextContent(/\S{3}/);
      expect(screen.queryByTestId("ct-part-lock")).toBeNull();
    },
  );

  it("указатель записи доходит до формы", () => {
    renderContent(
      <VersionPart {...props("fields", { at: "/meta_fields/3" })} />,
      "part=fields&at=%2Fmeta_fields%2F3",
    );
    expect(probe("probe-form").at).toBe("/meta_fields/3");
  });

  it("выпущенная версия: пометка и «Править копию»", () => {
    renderContent(
      <VersionPart {...props("fields", { readOnly: true })} />,
      "part=fields",
    );
    // Слов о выпуске на экране нет (они в плашке и у названия версии): замок с подсказкой.
    expect(screen.getByTestId("ct-part-lock")).not.toHaveTextContent(
      "выпущена",
    );
    expect(
      screen.getByRole("img", { name: /Версия выпущена/ }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("ct-part-copy"));
    expect(location()).toContain("copy=1");
  });

  it("«Сроки и сдача»: порядок подписания и подписи в точках сдачи в одной форме", () => {
    renderContent(<VersionPart {...props("deadlines")} />, "part=deadlines");
    expect(screen.getByTestId("ct-part-deadlines")).toHaveTextContent(
      "кто подписывает",
    );
    expect(probe("probe-form").section).toBe("submission");
  });

  it("правила проверки: файлы правил версии открываются в «Все файлы» на форме", () => {
    const rules = `${CONTENT_VERSION_DIR}/checks/format.yaml`;
    renderContent(<RulesPart {...props("rules")} />, "part=rules", {
      before: (client) => {
        client.setQueryData(
          packStudioKeys.tree(GALLERY_WORKSPACE.id),
          withFiles([
            rules,
            `${CONTENT_VERSION_DIR}/checks/deep/skip.yaml`,
            `${CONTENT_VERSION_DIR}/version.yaml`,
          ]),
        );
      },
    });
    expect(screen.getAllByTestId(/^ct-rule-file-/)).toHaveLength(1);
    fireEvent.click(screen.getByTestId("ct-rule-file-format.yaml"));
    expect(decodeURIComponent(location())).toContain(
      `part=files&file=${rules}`,
    );
  });

  it("правила проверки: без файлов правил блока нет", () => {
    renderContent(<RulesPart {...props("rules")} />, "part=rules", {
      before: (client) => {
        client.setQueryData(
          packStudioKeys.tree(GALLERY_WORKSPACE.id),
          withFiles([]),
        );
      },
    });
    expect(screen.queryByTestId("ct-rule-files")).toBeNull();
  });
});

describe("«Все файлы»", () => {
  beforeAll(async () => {
    await loadPackSpaceNamespace();
  });
  afterEach(cleanup);

  const seed = (paths: string[]) => ({
    before: (c: QueryClient) => {
      c.setQueryData(
        packStudioKeys.tree(GALLERY_WORKSPACE.id),
        withFiles(paths),
      );
    },
  });
  const text = `${CONTENT_VERSION_DIR}/files/common/meta.tex.j2`;

  it("без файла: подсказка выбрать файл и дерево; создание пака и шаблона по месту", () => {
    renderContent(
      <FilesPart {...props("files")} />,
      "part=files",
      seed([text]),
    );
    expect(screen.getByTestId("ct-files")).toHaveTextContent("Выберите файл");
    expect(screen.getByTestId("pack-tree")).toBeInTheDocument();
    expect(screen.getByTestId("probe-create")).toHaveTextContent("null");
    fireEvent.click(screen.getByTestId("tree-new-pack"));
    expect(probe("probe-create")).toEqual({ kind: "pack" });
    fireEvent.click(screen.getByTestId("tree-new-template-hse-cs-sse"));
    expect(probe("probe-create")).toEqual({
      kind: "template",
      pack: "hse-cs-sse",
    });
  });

  it("клик по файлу открывает его заменой записи", () => {
    const other = `${CONTENT_VERSION_DIR}/files/common/other.tex.j2`;
    renderContent(
      <FilesPart {...props("files", { file: text })} />,
      "part=files",
      seed([text, other]),
    );
    fireEvent.click(screen.getByTestId(`tree-file-${other}`));
    expect(decodeURIComponent(location())).toContain(`file=${other}`);
  });

  it("текстовый файл: редактор, формы нет", () => {
    renderContent(
      <FilesPart {...props("files", { file: text })} />,
      "part=files",
      seed([text]),
    );
    expect(probe("probe-text")).toEqual({ path: text, readOnly: false });
    expect(screen.queryByTestId("ct-fileview-form")).toBeNull();
  });

  it("файл правил открывается на форме, переключатель ведёт к тексту и обратно", () => {
    const rules = `${CONTENT_VERSION_DIR}/checks/format.yaml`;
    renderContent(
      <FilesPart {...props("files", { file: rules })} />,
      "part=files",
      seed([rules]),
    );
    expect(probe("probe-form").path).toBe(rules);
    fireEvent.click(screen.getByTestId("ct-fileview-text"));
    expect(probe("probe-text").path).toBe(rules);
    fireEvent.click(screen.getByTestId("ct-fileview-form"));
    expect(screen.getByTestId("probe-form")).toBeInTheDocument();
  });

  it("манифест версии: текст по умолчанию, форма по переключателю", () => {
    const manifest = `${CONTENT_VERSION_DIR}/version.yaml`;
    renderContent(
      <FilesPart {...props("files", { file: manifest })} />,
      "part=files",
      seed([manifest]),
    );
    expect(screen.getByTestId("probe-text")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("ct-fileview-form"));
    expect(probe("probe-form").section).toBeNull();
  });

  it("выпущенная версия: файл этой версии только для чтения, чужой путь замок версии не наследует", () => {
    renderContent(
      <FilesPart {...props("files", { file: text, readOnly: true })} />,
      "part=files",
      seed([text]),
    );
    expect(probe("probe-text").readOnly).toBe(true);
    cleanup();
    const other =
      "hse-cs-sse/templates/coursework/versions/2026.1.2/files/a.tex";
    renderContent(
      <FilesPart {...props("files", { file: other, readOnly: true })} />,
      "part=files",
      seed([other]),
    );
    expect(probe("probe-text").readOnly).toBe(false);
  });
});
