import { build, type Rolldown } from "vite";
import { describe, expect, it } from "vitest";

// Галерея состояний (/dev/sync-states) нужна только в разработке. Условие
// `import.meta.env.DEV` в маршрутах вычисляется при сборке, поэтому в рабочем
// бандле не должно быть ни самой страницы, ни записей галереи. Проверяем
// настоящей сборкой, а не чтением исходников: убрать код из бандла может только она.

type BuildOutput = Rolldown.RolldownOutput | Rolldown.RolldownOutput[];

const chunksOf = (result: unknown): { fileName: string; code: string }[] => {
  const outputs = (Array.isArray(result) ? result : [result]) as BuildOutput[];
  return outputs
    .flatMap((output) => (Array.isArray(output) ? output : [output]))
    .flatMap((output) => output.output)
    .flatMap((item) =>
      item.type === "chunk"
        ? [{ fileName: item.fileName, code: item.code }]
        : [],
    );
};

const FORBIDDEN = [
  "hse-dev-sync-states-gallery",
  "/dev/sync-states",
  // Записи галереи разных фич: все они живут в fixtures и тоже не должны попасть в бандл.
  "syncing_queued",
  "check_host_key_changed",
  "live_conflicts",
  "live_exchange_export",
  "profile_section_default",
];

describe("рабочая сборка", () => {
  it("не содержит галерею состояний синхронизации", async () => {
    const previous = process.env.NODE_ENV;
    // Сборка читает NODE_ENV, чтобы решить, что такое DEV; под тестами там «test».
    process.env.NODE_ENV = "production";
    try {
      const result = await build({
        mode: "production",
        logLevel: "silent",
        build: { write: false, minify: false, reportCompressedSize: false },
      });
      const chunks = chunksOf(result);
      expect(chunks.length).toBeGreaterThan(0);
      for (const chunk of chunks) {
        for (const marker of FORBIDDEN) {
          expect(
            chunk.code.includes(marker),
            `${chunk.fileName}: ${marker}`,
          ).toBe(false);
        }
      }
    } finally {
      if (previous === undefined) delete process.env.NODE_ENV;
      else process.env.NODE_ENV = previous;
    }
  }, 120_000);
});
