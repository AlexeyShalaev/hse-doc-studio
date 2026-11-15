import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CatalogCheckSchema, CatalogSourceSchema } from "../api/schemas";
import {
  hasBuiltinConflict,
  shortRevision,
  sortVersions,
  sourceLocation,
  verdictCounts,
} from "./report";

const FIXTURES = join(
  import.meta.dirname,
  "../../../../../../contracts/pack-catalog/fixtures",
);
const load = (dir: string, name: string): unknown =>
  JSON.parse(readFileSync(join(FIXTURES, dir, `${name}.json`), "utf8"));

const OK = CatalogCheckSchema.parse(load("CatalogCheck", "ok"));
const BLOCKED = CatalogCheckSchema.parse(load("CatalogCheck", "blocked"));

describe("помощники отчёта проверки", () => {
  it("считает версии по вердиктам", () => {
    expect(verdictCounts(OK)).toEqual({
      new: 2,
      incompatible: 1,
      unreleased: 1,
    });
  });

  it("видит конфликт со встроенным паком", () => {
    expect(hasBuiltinConflict(BLOCKED)).toBe(true);
    expect(hasBuiltinConflict(OK)).toBe(false);
  });

  it("ставит вперёд то, что мешает, затем то, что появится", () => {
    const versions = OK.packs[0]?.versions ?? [];
    expect(sortVersions([...versions].reverse()).map((v) => v.verdict)).toEqual(
      ["new", "new", "incompatible", "unreleased"],
    );
  });

  it("сокращает sha и дайджест, короткие ревизии оставляет", () => {
    expect(shortRevision("4b825dc642cb6eb9a060e54bf8d69288fbee4904")).toBe(
      "4b825dc6",
    );
    expect(shortRevision("v1")).toBe("v1");
  });

  it("называет место источника по виду", () => {
    expect(
      sourceLocation(
        CatalogSourceSchema.parse(load("CatalogSource", "git_applied")),
      ),
    ).toBe("https://git.example.org/acme/packs.git @ v2026.1.1");
    expect(
      sourceLocation(
        CatalogSourceSchema.parse(load("CatalogSource", "archive_failed")),
      ),
    ).toBe("packs-2026.zip");
    expect(
      sourceLocation(
        CatalogSourceSchema.parse(load("CatalogSource", "folder")),
      ),
    ).toBe("/Users/author/my-packs");
  });
});
