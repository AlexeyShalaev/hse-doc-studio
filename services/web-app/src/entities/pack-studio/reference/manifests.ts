import type { PackOutcome } from "../api/outcome";
import {
  PackModelPatchRequestSchema,
  type PackVersionModel,
} from "../api/schemas";

// Манифесты версий «на эталонах» для правки по месту (срез F7): модель версии, точечные правки с
// If-Match по ETag и пересчёт результата. Нужны только в разработке и тестах: экран правки
// проходит путь «править, увидеть дельту, отменить» без сервера. Пересчёт здесь игрушечный
// (две вещи: вид работы документа и условие слота подписи) и существует только в этой подмене;
// настоящий результат считает сервер, у клиента условий нет.

type Json = Record<string, unknown>;
type FileState = { path: string; etag: string; data: Json };
type Store = {
  counter: number;
  version: FileState;
  documents: Map<string, FileState>;
};

const DOC_IDS = [
  "operator_manual",
  "technical_specification",
  "shared_technical_specification",
  "project_proposal",
  "topic_application",
  "report",
  "presentation",
];

const docData = (id: string): Json => ({
  id,
  name: { ru: id },
  supported_kinds: [],
  supported_staffing: [],
  supported_langs: ["ru", "en"],
});

const versionData = (template: string): Json =>
  template === "vkr"
    ? {
        langs: ["ru", "en"],
        forms: [
          {
            id: "ai_declaration",
            sections: [
              {
                id: "main",
                fields: [
                  { id: "used_ai", type: "bool" },
                  {
                    id: "tools",
                    type: "text",
                    visible_if: { field: "used_ai", equals: true },
                  },
                ],
              },
            ],
          },
        ],
        checks_version: {},
      }
    : {
        langs: ["ru", "en"],
        pack_submission: {
          profiles: [
            {
              id: "topic-approval",
              items: [
                { doc_id: "project_proposal", signatures: ["supervisor"] },
                { doc_id: "topic_application", signatures: ["author"] },
              ],
              signing_route: [
                ["author"],
                ["supervisor", "co_supervisor"],
                ["academic_supervisor"],
              ],
              signing_slots: [
                {
                  doc_id: "topic_application",
                  slot_id: "co_supervisor",
                  when: { person: "co_supervisor" },
                },
                {
                  doc_id: "topic_application",
                  slot_id: "academic_supervisor",
                  when: { person: "supervisor", role: "company" },
                },
              ],
            },
          ],
        },
      };

const stores = new Map<string, Store>();

const keyOf = (id: string, pack: string, template: string, version: string) =>
  `${id}|${pack}|${template}|${version}`;

const storeOf = (
  id: string,
  pack: string,
  template: string,
  version: string,
): Store => {
  const key = keyOf(id, pack, template, version);
  let store = stores.get(key);
  if (!store) {
    const dir = `${pack}/templates/${template}/versions/${version}`;
    store = {
      counter: 0,
      version: {
        path: `${dir}/version.yaml`,
        etag: '"m-0"',
        data: versionData(template),
      },
      documents: new Map(
        DOC_IDS.map((doc) => [
          doc,
          {
            path: `${dir}/files/${doc}/doc.yaml`,
            etag: '"m-0"',
            data: docData(doc),
          },
        ]),
      ),
    };
    stores.set(key, store);
  }
  return store;
};

/** Сбросить манифесты подмены (между тестами). */
export const resetReferenceManifests = (): void => {
  stores.clear();
};

/** Изменить манифест мимо экрана: ETag меняется, правка экрана получит `stale_file`. */
export const touchReferenceManifest = (
  id: string,
  ref: { pack: string; template: string; version: string },
  file: string,
  mutate: (data: Json) => void,
): void => {
  const store = storeOf(id, ref.pack, ref.template, ref.version);
  const target =
    file === "version.yaml"
      ? store.version
      : store.documents.get(file.split("/")[1] ?? "");
  if (!target) return;
  mutate(target.data);
  store.counter += 1;
  target.etag = `"m-${String(store.counter)}"`;
};

const findFile = (
  id: string,
  path: string,
): { store: Store; file: FileState } | undefined => {
  for (const [key, store] of stores) {
    if (!key.startsWith(`${id}|`)) continue;
    if (store.version.path === path) return { store, file: store.version };
    for (const file of store.documents.values()) {
      if (file.path === path) return { store, file };
    }
  }
  return undefined;
};

/**
 * Файл манифеста целиком (`GET .../files/<путь>`): подмена хранит данные, а не YAML, поэтому
 * текст это JSON; прежний текст возвращается тем же, и ETag по нему тот же.
 */
export const readReferenceFile = (
  id: string,
  path: string,
): { text: string; etag: string } | undefined => {
  const found = findFile(id, path);
  return found
    ? { text: JSON.stringify(found.file.data), etag: found.file.etag }
    : undefined;
};

export type FileWrite =
  | { status: 200; etag: string; size: number }
  | { status: 404 }
  | { status: 409; etag: string };

/** Запись файла целиком (`PUT .../files/<путь>`) с `If-Match`: так откат возвращает прежний текст. */
export const writeReferenceFile = (
  id: string,
  path: string,
  body: unknown,
  ifMatch: string | null,
): FileWrite => {
  const found = findFile(id, path);
  if (!found) return { status: 404 };
  if (ifMatch !== null && ifMatch !== found.file.etag) {
    return { status: 409, etag: found.file.etag };
  }
  const text = typeof body === "string" ? body : JSON.stringify(body);
  found.file.data = JSON.parse(text) as Json;
  found.store.counter += 1;
  found.file.etag = `"m-${String(found.store.counter)}"`;
  return { status: 200, etag: found.file.etag, size: text.length };
};

/** Манифест версии для проверки в тестах. */
export const referenceManifest = (
  id: string,
  ref: { pack: string; template: string; version: string },
  file: string,
): Json | undefined => {
  const store = storeOf(id, ref.pack, ref.template, ref.version);
  return file === "version.yaml"
    ? store.version.data
    : store.documents.get(file.split("/")[1] ?? "")?.data;
};

export const referenceModel = (
  id: string,
  pack: string,
  template: string,
  version: string,
  changed: string[] = [],
): PackVersionModel => {
  const store = storeOf(id, pack, template, version);
  return structuredClone({
    workspace_id: id,
    pack,
    template,
    version,
    read_only: null,
    manifest: {
      path: store.version.path,
      etag: store.version.etag,
      data: store.version.data,
    },
    documents: [...store.documents.entries()].map(([doc, file]) => ({
      id: doc,
      manifest: { path: file.path, etag: file.etag, data: file.data },
      data: file.data,
      files: [],
      references: [],
    })),
    usage: [],
    checks: ["missing_figure_caption", "gost_margins"],
    problems: [],
    changed,
  });
};

// ── Точечные правки ──

type Op = {
  op: string;
  path: (string | number)[];
  value?: unknown;
  index?: number | null;
  to?: number | null;
};

class PatchConflict extends Error {}

const walk = (root: unknown, path: (string | number)[]): unknown => {
  let current = root;
  for (const key of path) {
    if (Array.isArray(current) && typeof key === "number")
      current = current[key];
    else if (
      current !== null &&
      typeof current === "object" &&
      typeof key === "string"
    ) {
      current = (current as Json)[key];
    } else throw new PatchConflict(`no node at ${path.join("/")}`);
  }
  return current;
};

const applyOp = (data: Json, op: Op): void => {
  if (op.op === "insert") {
    const list = walk(data, op.path);
    if (!Array.isArray(list) || op.index === null || op.index === undefined) {
      throw new PatchConflict("not a list");
    }
    list.splice(op.index, 0, structuredClone(op.value));
    return;
  }
  if (op.op === "move") {
    const list = walk(data, op.path);
    if (!Array.isArray(list) || op.index == null || op.to == null) {
      throw new PatchConflict("not a list");
    }
    const item: unknown = list.splice(op.index, 1)[0];
    list.splice(op.to, 0, item);
    return;
  }
  const key = op.path[op.path.length - 1];
  const parent = walk(data, op.path.slice(0, -1));
  if (key === undefined) throw new PatchConflict("root");
  if (op.op === "set") {
    if (Array.isArray(parent) && typeof key === "number")
      parent[key] = structuredClone(op.value);
    else if (parent !== null && typeof parent === "object")
      (parent as Json)[String(key)] = structuredClone(op.value);
    else throw new PatchConflict("no parent");
    return;
  }
  if (op.op === "delete") {
    if (Array.isArray(parent) && typeof key === "number") {
      if (key >= parent.length) throw new PatchConflict("no item");
      parent.splice(key, 1);
    } else if (
      parent !== null &&
      typeof parent === "object" &&
      String(key) in parent
    ) {
      Reflect.deleteProperty(parent, String(key));
    } else throw new PatchConflict("no key");
    return;
  }
  throw new PatchConflict(`unsupported ${op.op}`);
};

export type PatchOutcome =
  | { status: 200; model: PackVersionModel }
  | { status: 409; code: "stale_file"; etag: string }
  | {
      status: 422;
      code: "model_invalid" | "yaml_patch_conflict";
      reason: string;
    };

/** Что подмена отвечает на `PATCH .../model`: ETag, схема тела, правки по порядку. */
export const patchReferenceModel = (
  id: string,
  pack: string,
  template: string,
  version: string,
  body: unknown,
  ifMatch: string | null,
): PatchOutcome => {
  const parsed = PackModelPatchRequestSchema.safeParse(body);
  if (!parsed.success) {
    return {
      status: 422,
      code: "model_invalid",
      reason: "body does not match the schema",
    };
  }
  const store = storeOf(id, pack, template, version);
  const { file, ops } = parsed.data;
  const target =
    file === "version.yaml"
      ? store.version
      : store.documents.get(file.split("/")[1] ?? "");
  if (!target) {
    return {
      status: 422,
      code: "model_invalid",
      reason: "file must be version.yaml or a doc.yaml",
    };
  }
  if (ifMatch !== null && ifMatch !== target.etag) {
    return { status: 409, code: "stale_file", etag: target.etag };
  }
  const draft = structuredClone(target.data);
  try {
    for (const op of ops) applyOp(draft, op as Op);
  } catch (error) {
    return {
      status: 422,
      code: "yaml_patch_conflict",
      reason: error instanceof Error ? error.message : "conflict",
    };
  }
  // Ограничение схемы, которое подмена проверяет: слот подписи без документа не пишется.
  const bad = JSON.stringify(draft).includes('"doc_id":""');
  if (bad) {
    return {
      status: 422,
      code: "model_invalid",
      reason: "doc_id must not be empty",
    };
  }
  target.data = draft;
  store.counter += 1;
  target.etag = `"m-${String(store.counter)}"`;
  return {
    status: 200,
    model: referenceModel(id, pack, template, version, [target.path]),
  };
};

// ── Игрушечный пересчёт результата по правленым манифестам ──

const asList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];

const whenHolds = (when: unknown, inputs: Record<string, string>): boolean => {
  if (when === null || typeof when !== "object") return true;
  const { person, role } = when as { person?: string; role?: string };
  if (!person) return true;
  const value = inputs[person] ?? "no";
  if (value === "no") return false;
  return role === undefined || value === role;
};

/**
 * Результат эталона с учётом правки манифестов: вид работы документа выключает документ, условие
 * слота подписи переносит пару между «в маршруте» и «пропущена». Остальное как в эталоне.
 */
export const applyReferenceEdits = (
  outcome: PackOutcome,
  id: string,
  pack: string,
  template: string,
  version: string,
): PackOutcome => {
  const store = stores.get(keyOf(id, pack, template, version));
  if (!store || store.counter === 0) return outcome;
  const out = structuredClone(outcome);
  for (const doc of out.documents) {
    const kinds = asList(store.documents.get(doc.id)?.data.supported_kinds);
    if (
      kinds.length > 0 &&
      !kinds.includes(out.inputs.kind ?? "") &&
      doc.state === "active"
    ) {
      doc.state = "inactive";
    }
  }
  const profiles = ((store.version.data.pack_submission as Json | undefined)
    ?.profiles ?? []) as Json[];
  for (const point of out.points) {
    const profile = profiles[point.index];
    const slots = (profile?.signing_slots ?? []) as Json[];
    for (const slot of slots) {
      const doc = String(slot.doc_id);
      const id2 = String(slot.slot_id);
      const holds = whenHolds(slot.when, out.inputs);
      const pair = point.route.pairs.find(
        (p) => p.doc_id === doc && p.slot_id === id2,
      );
      const skipped = point.route.skipped.find(
        (p) => p.doc_id === doc && p.slot_id === id2,
      );
      if (pair && !holds && pair.source === "preset") {
        point.route.pairs = point.route.pairs.filter((p) => p !== pair);
        point.route.skipped.push({
          doc_id: doc,
          slot_id: id2,
          when: pair.when,
          why: pair.why,
        });
        point.route.steps = point.route.steps
          .map((step) => step.filter((p) => p.persona !== pair.persona))
          .filter((step) => step.length > 0);
      } else if (skipped && holds) {
        point.route.skipped = point.route.skipped.filter((p) => p !== skipped);
        point.route.pairs.push({
          doc_id: doc,
          slot_id: id2,
          persona: id2,
          source: "preset",
          optional: false,
          when: skipped.when,
          why: skipped.why,
        });
      }
    }
  }
  out.revision = `${out.revision}-m${String(store.counter)}`;
  out.fingerprint = `${out.fingerprint}-m${JSON.stringify([...store.documents.values()].map((d) => d.data)).length}${JSON.stringify(store.version.data).length}`;
  return out;
};
