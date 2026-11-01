// Проверка рабочей сборки: галерея состояний синхронизации (/dev/sync-states)
// существует только в разработке, и ни её страницы, ни её записей в dist быть не
// должно. Запускать после `pnpm build`.
import fs from "node:fs";
import path from "node:path";

const DIST = path.resolve(import.meta.dirname, "..", "dist");

// Строки, которые есть только в коде галереи (метка страницы и маршрут).
const MARKERS = [
  "hse-dev-sync-states-gallery",
  "/dev/sync-states",
  // Галерея серверных экранов и демо-мир сервера (VITE_SERVER_DEMO).
  "hse-dev-server-screens-gallery",
  "/dev/server-screens",
  "server-demo-world",
];

const walk = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(file) : [file];
  });

if (!fs.existsSync(DIST)) {
  console.error("dist/ не найден: сначала выполните `pnpm build`.");
  process.exit(2);
}

const found = [];
for (const file of walk(DIST)) {
  if (!/\.(js|mjs|css|html)$/.test(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  for (const marker of MARKERS) {
    if (text.includes(marker))
      found.push(`${path.relative(DIST, file)}: ${marker}`);
  }
}

if (found.length > 0) {
  console.error("В рабочую сборку попала галерея состояний:");
  for (const line of found) console.error(`  ${line}`);
  process.exit(1);
}
console.log("Галереи состояний в рабочей сборке нет.");
