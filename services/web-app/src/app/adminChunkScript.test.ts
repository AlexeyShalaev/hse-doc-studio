import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const SCRIPT = join(
  import.meta.dirname,
  "../../scripts/verify-admin-chunk.mjs",
);

// Словари админки берутся из репозитория: на каждый файл admin/<name>.json
// сборка даёт по чанку на язык.
const ADMIN_LOCALES = join(
  import.meta.dirname,
  "../shared/lib/i18n/locales/ru/admin",
);
const dictionaries = (): string[] =>
  readdirSync(ADMIN_LOCALES).map((f) => f.replace(/\.json$/, ""));

const dirs: string[] = [];
const fixture = (
  entry: string,
  admin: string | null,
  skipDictionary?: string,
): string => {
  const dist = mkdtempSync(join(tmpdir(), "admin-chunk-"));
  dirs.push(dist);
  mkdirSync(join(dist, "assets"));
  writeFileSync(
    join(dist, "index.html"),
    '<script type="module" src="/assets/index-aaa.js"></script>',
  );
  writeFileSync(join(dist, "assets/index-aaa.js"), entry);
  if (admin !== null) writeFileSync(join(dist, "assets/admin-bbb.js"), admin);
  for (const name of dictionaries()) {
    if (name === skipDictionary) continue;
    for (const lng of ["ru", "en"]) {
      writeFileSync(
        join(dist, `assets/locale-admin-${name}-${lng}-ccc.js`),
        "{}",
      );
    }
  }
  return dist;
};

const run = (dist: string): { code: number; out: string } => {
  try {
    const out = execFileSync("node", [SCRIPT], {
      env: { ...process.env, DIST_DIR: dist },
      encoding: "utf8",
      stdio: "pipe",
    });
    return { code: 0, out };
  } catch (error) {
    const e = error as { status: number; stderr: string };
    return { code: e.status, out: e.stderr };
  }
};

afterEach(() => {
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true });
});

describe("verify:admin-chunk", () => {
  it("passes when the marker lives only in the admin chunk", () => {
    const dist = fixture("console.log(1)", 'x="hse-admin-chunk-marker"');
    expect(run(dist).code).toBe(0);
  });

  it("fails when the marker leaks into the entry", () => {
    const dist = fixture(
      'x="hse-admin-chunk-marker"',
      'x="hse-admin-chunk-marker"',
    );
    const result = run(dist);
    expect(result.code).toBe(1);
    expect(result.out).toContain("index-aaa.js");
  });

  it("fails when there is no admin chunk", () => {
    expect(run(fixture("console.log(1)", null)).code).toBe(1);
  });

  it("fails when a page dictionary has no chunk", () => {
    const dist = fixture(
      "console.log(1)",
      'x="hse-admin-chunk-marker"',
      "runners",
    );
    const result = run(dist);
    expect(result.code).toBe(1);
    expect(result.out).toContain("admin/runners");
  });
});
