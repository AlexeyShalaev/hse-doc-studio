import { describe, expect, it } from "vitest";
import type { PackFileChange } from "@entities/pack-studio";
import { GALLERY_REF } from "../galleryKit";
import {
  baseDirOf,
  findSameFiles,
  freshCopyDir,
  mineOf,
  sameManifest,
  scanCandidates,
  type CopyReaders,
} from "./copyEdits";

const NEW = "hse-cs-sse/templates/coursework/versions/2026.1.3";
const OLD = "hse-cs-sse/templates/coursework/versions/2026.1.2";
const added = (path: string): PackFileChange => ({ path, status: "added" });

const copyOf = (names: string[]): PackFileChange[] => [
  added(`${NEW}/version.yaml`),
  ...names.map((name) => added(`${NEW}/${name}`)),
];

describe("freshCopyDir", () => {
  it("копия: новый version.yaml открытой версии", () => {
    expect(freshCopyDir(copyOf(["files/ts/doc.yaml"]), GALLERY_REF)).toBe(NEW);
  });

  it("версия уже была в основной ветке: version.yaml изменён, а не новый", () => {
    expect(
      freshCopyDir(
        [{ path: `${NEW}/version.yaml`, status: "modified" }],
        GALLERY_REF,
      ),
    ).toBeNull();
  });

  it("новая версия, но не открытая: открытая не копия", () => {
    expect(
      freshCopyDir(copyOf([]), { ...GALLERY_REF, version: "2026.1.2" }),
    ).toBeNull();
  });
});

describe("пути копии и основы", () => {
  it("каталог основы лежит рядом с копией", () => {
    expect(baseDirOf(NEW, "2026.1.2")).toBe(OLD);
  });

  it("сверяем новые файлы каталога, без манифеста версии", () => {
    expect(
      scanCandidates(
        [
          ...copyOf(["files/ts/doc.yaml", "files/ts/ts.ru.tex"]),
          { path: `${NEW}/files/x.tex`, status: "modified" },
          added("hse-cs-sse/pack.yaml"),
        ],
        NEW,
      ),
    ).toEqual([`${NEW}/files/ts/doc.yaml`, `${NEW}/files/ts/ts.ru.tex`]);
  });
});

describe("sameManifest", () => {
  it("номер, статус, выпуск и заметки пишет Студия: на сравнение не влияют", () => {
    expect(
      sameManifest(
        { id: "2026.1.3", status: "beta", changes: { ru: ["а"] }, kinds: [1] },
        { id: "2026.1.2", status: "stable", release: {}, kinds: [1] },
      ),
    ).toBe(true);
  });

  it("правка условий версии видна, порядок ключей не важен", () => {
    expect(
      sameManifest(
        { a: 1, supported_kinds: ["x", "y"] },
        { supported_kinds: ["x", "y"], a: 1 },
      ),
    ).toBe(true);
    expect(
      sameManifest({ supported_kinds: ["x"] }, { supported_kinds: ["x", "y"] }),
    ).toBe(false);
  });
});

const readers = (
  mine: Record<string, string | null>,
  base: Record<string, string | null>,
  manifest = true,
): CopyReaders => ({
  draft: (path) => Promise.resolve(mine[path] ?? null),
  base: (path) => Promise.resolve(base[path] ?? null),
  manifest: () => Promise.resolve(manifest),
});

describe("findSameFiles: что человек не трогал", () => {
  const paths = [
    `${NEW}/files/ts/doc.yaml`,
    `${NEW}/files/ts/ts.ru.tex`,
    `${NEW}/files/ts/new.tex`,
    `${NEW}/files/pz/pz.ru.tex`,
  ];

  it("87 файлов копии, правок три: остаётся только то, что отличается или новое", async () => {
    const same = await findSameFiles(
      NEW,
      OLD,
      paths,
      readers(
        {
          [paths[0] ?? ""]: '"b"',
          [paths[1] ?? ""]: '"t2"',
          [paths[2] ?? ""]: '"n"',
          [paths[3] ?? ""]: '"p"',
        },
        {
          [`${OLD}/files/ts/doc.yaml`]: '"a"',
          [`${OLD}/files/ts/ts.ru.tex`]: '"t2"',
          [`${OLD}/files/pz/pz.ru.tex`]: '"p"',
        },
      ),
    );
    expect([...same].sort()).toEqual(
      [
        `${NEW}/files/ts/ts.ru.tex`,
        `${NEW}/files/pz/pz.ru.tex`,
        `${NEW}/version.yaml`,
      ].sort(),
    );
  });

  it("файл, который не прочитался, не считается совпавшим", async () => {
    const same = await findSameFiles(
      NEW,
      OLD,
      [`${NEW}/a.tex`],
      readers({ [`${NEW}/a.tex`]: null }, { [`${OLD}/a.tex`]: null }, false),
    );
    expect([...same]).toEqual([]);
  });

  it("манифест версии с другими условиями остаётся в списке правок", async () => {
    const same = await findSameFiles(NEW, OLD, [], readers({}, {}, false));
    expect(same.has(`${NEW}/version.yaml`)).toBe(false);
  });

  it("сбой чтения манифеста не ломает сверку", async () => {
    const same = await findSameFiles(NEW, OLD, [`${NEW}/a.tex`], {
      draft: () => Promise.resolve("x"),
      base: () => Promise.resolve("x"),
      manifest: () => Promise.reject(new Error("boom")),
    });
    expect([...same]).toEqual([`${NEW}/a.tex`]);
  });
});

describe("mineOf", () => {
  it("убирает совпавшие файлы; без сверки список как есть", () => {
    const list = copyOf(["a.tex", "b.tex"]);
    expect(mineOf(list, null)).toEqual(list);
    expect(
      mineOf(list, new Set([`${NEW}/version.yaml`, `${NEW}/a.tex`])),
    ).toEqual([added(`${NEW}/b.tex`)]);
  });
});
