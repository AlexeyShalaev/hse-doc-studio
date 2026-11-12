// One-off verifier: every STATIC t("...") / i18n.t("ns:...") key in src/
// resolves to a leaf (or plural base) in the corresponding ru locale JSON.
// Dynamic template-literal keys are skipped (can't resolve statically).
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..", "src");
const LOC = path.join(ROOT, "shared/lib/i18n/locales/ru");
const cache = {};
const LAZY_PAGE_NAMESPACES = ["landing", "signing"];
const load = (ns) => {
  if (ns in cache) return cache[ns];
  // Словари админки: admin<Name> живёт в locales/ru/admin/<name>.json.
  const admin = /^admin([A-Z][A-Za-z]*)$/.exec(ns);
  // Ленивые словари страниц: locales/ru/<ns>/<ns>.json (лендинг, страница подписанта).
  const file = LAZY_PAGE_NAMESPACES.includes(ns)
    ? path.join(LOC, ns, ns + ".json")
    : admin
      ? path.join(
          LOC,
          "admin",
          admin[1].charAt(0).toLowerCase() + admin[1].slice(1) + ".json",
        )
      : path.join(LOC, ns + ".json");
  try {
    const dict = JSON.parse(fs.readFileSync(file, "utf8"));
    // Тексты редких окон страницы подписанта дописываются в то же пространство (signing/rare.json).
    if (ns === "signing") {
      const rare = JSON.parse(
        fs.readFileSync(path.join(LOC, "signing", "rare.json"), "utf8"),
      );
      return (cache[ns] = merge(dict, rare));
    }
    return (cache[ns] = dict);
  } catch {
    return (cache[ns] = null);
  }
};
const merge = (base, extra) => {
  const out = { ...base };
  for (const [key, value] of Object.entries(extra)) {
    out[key] =
      value &&
      typeof value === "object" &&
      out[key] &&
      typeof out[key] === "object"
        ? merge(out[key], value)
        : value;
  }
  return out;
};
const PLURALS = ["_one", "_few", "_many", "_two", "_other", "_zero"];
const has = (obj, key) => {
  const parts = key.split(".");
  let cur = obj;
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (cur && typeof cur === "object" && p in cur) {
      cur = cur[p];
      continue;
    }
    if (
      i === parts.length - 1 &&
      cur &&
      typeof cur === "object" &&
      PLURALS.some((s) => p + s in cur)
    )
      return true;
    return false;
  }
  return true;
};
const walk = (d) =>
  fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => {
    const f = path.join(d, e.name);
    return e.isDirectory() ? walk(f) : [f];
  });

const files = walk(ROOT).filter(
  (f) =>
    /\.(tsx|ts)$/.test(f) &&
    !/\.test\./.test(f) &&
    !/\.stories\./.test(f) &&
    !path.relative(ROOT, f).includes("i18n"),
);
let misses = 0,
  checked = 0;
const rel = (f) => path.relative(ROOT, f).replace(/\\/g, "/");
for (const f of files) {
  const src = fs.readFileSync(f, "utf8");
  const nsMatch = src.match(/useTranslation\(\s*["']([A-Za-z]+)["']/);
  const defNs = nsMatch ? nsMatch[1] : null;
  let m;
  const re = /(?:^|[^.\w])t\(\s*["']([A-Za-z0-9_.:]+)["']/g;
  while ((m = re.exec(src))) {
    let key = m[1],
      ns = defNs;
    if (key.includes(":")) [ns, key] = key.split(":");
    if (!ns) continue;
    const obj = load(ns);
    checked++;
    if (!obj) {
      console.log("NO-NS  " + ns + " in " + rel(f));
      misses++;
    } else if (!has(obj, key)) {
      console.log("MISS   " + ns + ":" + key + " in " + rel(f));
      misses++;
    }
  }
  const re2 = /i18n\.t\(\s*["']([A-Za-z]+):([A-Za-z0-9_.]+)["']/g;
  while ((m = re2.exec(src))) {
    const ns = m[1],
      key = m[2];
    const obj = load(ns);
    checked++;
    if (!obj) {
      console.log("NO-NS  " + ns + " in " + rel(f));
      misses++;
    } else if (!has(obj, key)) {
      console.log("MISS   " + ns + ":" + key + " in " + rel(f));
      misses++;
    }
  }
}
console.log(
  "\nChecked " +
    checked +
    " static t() keys across " +
    files.length +
    " files; " +
    misses +
    " unresolved.",
);
