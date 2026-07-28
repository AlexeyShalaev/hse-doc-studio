import { describe, expect, it } from "vitest";

import {
  buildDocRefIndex,
  docHrefForId,
  docIdFromHref,
  isDocHref,
  remarkDocLinks,
} from "./docLinks";

type MdastNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MdastNode[];
};

const paragraph = (text: string): MdastNode => ({
  type: "root",
  children: [{ type: "paragraph", children: [{ type: "text", value: text }] }],
});

const toDocs = (docIds: string[]): { id: string }[] =>
  docIds.map((id) => ({ id }));

const linkify = (text: string, docIds: string[]): MdastNode[] => {
  const tree = paragraph(text);
  remarkDocLinks(buildDocRefIndex(toDocs(docIds)))()(tree);
  return tree.children?.[0]?.children ?? [];
};

describe("docLinks helpers", () => {
  it("builds an in-app href and round-trips the doc scheme", () => {
    expect(docHrefForId("p1", "thesis")).toBe("/projects/p1/documents/thesis");
    expect(isDocHref("doc:thesis")).toBe(true);
    expect(isDocHref("https://x")).toBe(false);
    expect(isDocHref(undefined)).toBe(false);
    expect(docIdFromHref("doc:technical_specification")).toBe(
      "technical_specification",
    );
  });
});

const findIn = (
  index: ReturnType<typeof buildDocRefIndex>,
  token: string,
): string | undefined => {
  if (!index.regex) return undefined;
  index.regex.lastIndex = 0;
  const match = index.regex.exec(token);
  return match ? index.lookup(match[0]) : undefined;
};

describe("buildDocRefIndex", () => {
  it("maps code, name, id and file paths back to the doc id", () => {
    const index = buildDocRefIndex(
      toDocs(["thesis", "technical_specification"]),
    );
    const find = (token: string): string | undefined => findIn(index, token);
    expect(find("ВКР")).toBe("thesis");
    expect(find("thesis")).toBe("thesis");
    expect(find("Выпускная квалификационная работа")).toBe("thesis");
    expect(find("thesis/thesis.tex")).toBe("thesis");
    expect(find("technical_specification/technical_specification.pdf")).toBe(
      "technical_specification",
    );
  });

  it("returns a null regex when the project has no documents", () => {
    expect(buildDocRefIndex([]).regex).toBeNull();
  });

  it("keeps owned team instances unambiguous: no bare type tokens", () => {
    const index = buildDocRefIndex([
      {
        id: "thesis--ivanov",
        def_id: "thesis",
        owner: "ivanov",
        owner_name: "Иванов И. И.",
        source_file: "ivanov/thesis/thesis.tex",
        output_file: "ivanov/thesis/thesis.pdf",
      },
    ]);
    const find = (token: string): string | undefined => findIn(index, token);
    // Bare code/id would resolve to an arbitrary author's copy — excluded.
    expect(find("ВКР")).toBeUndefined();
    expect(find("thesis")).toBeUndefined();
    // Unique instance tokens still resolve.
    expect(find("thesis--ivanov")).toBe("thesis--ivanov");
    expect(find("ivanov/thesis/thesis.tex")).toBe("thesis--ivanov");
    expect(find("ВКР — Иванов И. И.")).toBe("thesis--ivanov");
  });
});

describe("remarkDocLinks", () => {
  it("linkifies document codes and file paths in prose", () => {
    const parts = linkify(
      "См. ВКР и technical_specification/technical_specification.tex.",
      ["thesis", "technical_specification"],
    );
    expect(parts).toEqual([
      { type: "text", value: "См. " },
      {
        type: "link",
        url: "doc:thesis",
        children: [{ type: "text", value: "ВКР" }],
      },
      { type: "text", value: " и " },
      {
        type: "link",
        url: "doc:technical_specification",
        children: [
          {
            type: "text",
            value: "technical_specification/technical_specification.tex",
          },
        ],
      },
      { type: "text", value: "." },
    ]);
  });

  it("prefers the longest match so a file path wins over the bare id", () => {
    const parts = linkify("thesis/thesis.tex", ["thesis"]);
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({ type: "link", url: "doc:thesis" });
  });

  it("does not match a doc id hidden inside another word", () => {
    // "thesis" is a substring of "synthesis" — must not linkify.
    const parts = linkify("Слово synthesis не трогаем", ["thesis"]);
    expect(parts.every((node) => node.type !== "link")).toBe(true);
  });

  it("leaves text inside existing links untouched", () => {
    const tree: MdastNode = {
      type: "root",
      children: [
        {
          type: "link",
          url: "https://example.com",
          children: [{ type: "text", value: "ВКР" }],
        },
      ],
    };
    remarkDocLinks(buildDocRefIndex(toDocs(["thesis"])))()(tree);
    const link = tree.children?.[0];
    expect(link?.children).toEqual([{ type: "text", value: "ВКР" }]);
  });
});
