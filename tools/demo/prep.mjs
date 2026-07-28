// Пересобирает тезисы демо-проектов через API запущенного демо-инстанса.
// Зачем: титульные листы получают группу БПИ222 (сев патчит паспорт), а русский
// тезис — живые находки типографики (сев вносит пару огрехов в .tex).
// Требует: `make demo-up` в соседнем терминале + запущенный Docker (TeX Live).
//
// Запуск: node tools/demo/prep.mjs   (или через make shots-prep)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE || "http://127.0.0.1:17777";
const MANIFEST = JSON.parse(readFileSync(resolve(HERE, ".build/demo/manifest.json"), "utf-8"));

const TARGETS = [
  [MANIFEST.ru.id, "thesis", "ru/thesis"],
  [MANIFEST.en.id, "thesis", "en/thesis"],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function latestCompile(project, doc) {
  const res = await fetch(`${BASE}/api/v1/projects/${project}/documents/${doc}/compiles`);
  if (!res.ok) return null;
  const list = await res.json();
  return list[0] || null;
}

for (const [project, doc, label] of TARGETS) {
  process.stdout.write(`→ rebuild ${label} … `);
  const res = await fetch(`${BASE}/api/v1/projects/${project}/documents/${doc}/compile`, { method: "POST" });
  if (!res.ok) {
    console.log(`FAIL trigger: HTTP ${res.status} ${(await res.text()).slice(0, 120)}`);
    continue;
  }
  // ждём завершения: свежая запись сборки со статусом не running/pending
  let status = "running";
  for (let i = 0; i < 180; i++) {
    await sleep(2000);
    const rec = await latestCompile(project, doc);
    status = rec?.status || "unknown";
    if (status !== "running" && status !== "pending" && status !== "queued") break;
  }
  console.log(status);
}
console.log("PREP_DONE");
