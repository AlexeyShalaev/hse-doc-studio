// Проверка рабочей сборки: админка живёт в отдельном lazy-чанке admin
// (assets/admin-*.js). Код и ключи админки не должны попасть в entry и в
// чанки экранов без сессии, а index.html не должен заранее подгружать чанк.
// Запускать после `pnpm build`.
import fs from "node:fs";
import path from "node:path";

const DIST = process.env.DIST_DIR
  ? path.resolve(process.env.DIST_DIR)
  : path.resolve(import.meta.dirname, "..", "dist");

// Метка из кода чанка и пространство имён словарей админки.
const MARKERS = ["hse-admin-chunk-marker", "adminShell"];

if (!fs.existsSync(DIST)) {
  console.error("dist/ не найден: сначала выполните `pnpm build`.");
  process.exit(2);
}

const assets = path.join(DIST, "assets");
const files = fs.existsSync(assets)
  ? fs.readdirSync(assets).filter((f) => f.endsWith(".js"))
  : [];
const read = (f) => fs.readFileSync(path.join(assets, f), "utf8");
const problems = [];

const adminChunks = files.filter((f) => /^admin-[^.]+\.js$/.test(f));
if (adminChunks.length !== 1) {
  problems.push(
    `ожидался ровно один чанк assets/admin-*.js, найдено: ${adminChunks.length}`,
  );
} else if (!read(adminChunks[0]).includes(MARKERS[0])) {
  problems.push(`в ${adminChunks[0]} нет метки ${MARKERS[0]}`);
}

// Словари админки: каждый admin/<name>.json в каждом языке уходит в свой чанк
// locale-admin-<name>-<lng>-*.js, а у каждого такого словаря есть жёсткий
// бюджет в .size-limit.json (без бюджета размер словаря никто не сторожит).
const localesDir = path.resolve(
  import.meta.dirname,
  "..",
  "src/shared/lib/i18n/locales",
);
const names = fs
  .readdirSync(path.join(localesDir, "ru", "admin"))
  .filter((f) => f.endsWith(".json"))
  .map((f) => f.slice(0, -".json".length));
for (const name of names) {
  for (const lng of ["ru", "en"]) {
    const re = new RegExp(`^locale-admin-${name}-${lng}-[^.]+\\.js$`);
    if (files.filter((f) => re.test(f)).length !== 1) {
      problems.push(`нет ровно одного чанка словаря admin/${name} (${lng})`);
    }
  }
}
const budgets = JSON.parse(
  fs.readFileSync(
    path.resolve(import.meta.dirname, "..", ".size-limit.json"),
    "utf8",
  ),
).map((entry) => entry.path);
for (const name of names) {
  if (!budgets.includes(`dist/assets/locale-admin-${name}-*.js`)) {
    problems.push(`у словаря admin/${name} нет бюджета в .size-limit.json`);
  }
}
for (const budget of budgets) {
  const m = /locale-admin-([A-Za-z]+)-\*\.js$/.exec(budget);
  if (m?.[1] && !names.includes(m[1])) {
    problems.push(`бюджет ${budget} без словаря admin/${m[1]}.json`);
  }
}
if (
  files.some(
    (f) =>
      /^locale-admin-[^-]+-[a-z]{2}-/.test(f) === false &&
      f.startsWith("locale-admin-"),
  )
) {
  problems.push("чанк словаря админки с неожиданным именем");
}

const html = fs.readFileSync(path.join(DIST, "index.html"), "utf8");
const entries = [...html.matchAll(/<script[^>]+src="\/?assets\/([^"]+\.js)"/g)]
  .map((m) => m[1])
  .filter((f) => files.includes(f));
if (entries.length === 0) problems.push("в index.html не найден entry-скрипт");
if (/<link[^>]+(?:modulepreload|preload)[^>]+assets\/admin-/.test(html)) {
  problems.push("index.html заранее подгружает чанк admin");
}

// Чанки, нужные до входа (экраны auth), и entry не содержат админку.
const outside = new Set([
  ...entries,
  ...files.filter((f) =>
    /^(Login|Register|Forgot|Reset|Invite|Verify|FirstRun|AuthError)/.test(f),
  ),
]);
for (const f of outside) {
  const text = read(f);
  for (const marker of MARKERS) {
    if (text.includes(marker)) problems.push(`${f}: ${marker}`);
  }
}

if (problems.length > 0) {
  console.error("Чанк админки изолирован плохо:");
  for (const line of problems) console.error(`  ${line}`);
  process.exit(1);
}
console.log(
  `Чанк админки изолирован: ${adminChunks[0]}, проверено ${outside.size} файл(ов) вне него.`,
);
