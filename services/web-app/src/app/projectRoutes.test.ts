import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Переезд инструментов на собственные маршруты оставил в коде ссылки прежнего
// вида — `/projects/<id>/documents/signatures`. Такая ссылка не падает в 404:
// «signatures» подставляется как `:docId`, и пользователь получает живую
// страницу «Документ не найден». Глазами это не ловится, поэтому сверяем
// автоматически: первый сегмент после id обязан быть объявленным маршрутом.

const SRC = join(import.meta.dirname, "..");
const ROUTER = join(import.meta.dirname, "router.tsx");

const collectSourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return collectSourceFiles(full);
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [full] : [];
  });

const declaredSegments = (): Set<string> => {
  const router = readFileSync(ROUTER, "utf8");
  const segments = new Set<string>();
  for (const [, segment] of router.matchAll(
    /path:\s*"\/projects\/:projectId\/([^/"]+)/g,
  )) {
    if (segment) segments.add(segment);
  }
  return segments;
};

// `/projects/${...}/<сегмент>` — интересует только литеральный первый сегмент.
const LINK_RE = /\/projects\/\$\{[^}]+\}\/([a-z][a-z0-9-]*)/g;
// Тот же путь бывает и адресом API (`apiClient.get('/projects/${id}/forms')`),
// а там сегменты свои. Отличаем по вызову навигации в той же строке.
const NAVIGATION_RE = /navigate\(|\bto=\{|\bhref=\{/;

describe("ссылки на разделы проекта", () => {
  it("ведут только на объявленные маршруты", () => {
    const known = declaredSegments();
    expect(known.size).toBeGreaterThan(0);

    const broken: string[] = [];
    for (const file of collectSourceFiles(SRC)) {
      readFileSync(file, "utf8")
        .split("\n")
        .forEach((line, index) => {
          if (!NAVIGATION_RE.test(line)) return;
          for (const [link, segment] of line.matchAll(LINK_RE)) {
            if (segment && !known.has(segment)) {
              broken.push(
                `${file.slice(SRC.length + 1)}:${String(index + 1)}: ${link}`,
              );
            }
          }
        });
    }

    expect(broken).toEqual([]);
  });
});
