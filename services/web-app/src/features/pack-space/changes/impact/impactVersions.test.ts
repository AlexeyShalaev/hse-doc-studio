import { describe, expect, it } from "vitest";
import { impactVersions } from "./impactVersions";

const file = (path: string, status: "added" | "modified" | "deleted") => ({
  path,
  status,
});
const v = (version: string) =>
  `hse-cs-sse/templates/coursework/versions/${version}`;

describe("версии с правками для «до и после»", () => {
  it("берёт версии изменённых файлов, без дублей, версия экрана первая", () => {
    const { versions, extra } = impactVersions(
      [
        file(`${v("2026.1.7")}/version.yaml`, "modified"),
        file(`${v("2026.1.7")}/files/a.tex`, "added"),
        file(`${v("2026.1.6")}/version.yaml`, "modified"),
      ],
      { pack: "hse-cs-sse", template: "coursework", version: "2026.1.7" },
    );
    expect(versions.map((x) => x.version)).toEqual(["2026.1.7", "2026.1.6"]);
    expect(extra).toBe(0);
  });

  it("удалённые файлы и манифесты вне версий версию не дают", () => {
    const { versions } = impactVersions([
      file(`${v("2026.1.7")}/version.yaml`, "deleted"),
      file("hse-cs-sse/pack.yaml", "modified"),
    ]);
    expect(versions).toEqual([]);
  });

  it("больше трёх версий: считаются три, остальные в extra", () => {
    const { versions, extra } = impactVersions(
      ["1", "2", "3", "4", "5"].map((n) =>
        file(`${v(`2026.1.${n}`)}/version.yaml`, "modified"),
      ),
    );
    expect(versions).toHaveLength(3);
    expect(extra).toBe(2);
  });
});
