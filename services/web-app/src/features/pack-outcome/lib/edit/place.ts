import type { PackVersionModel } from "@entities/pack-studio";
import { resolvePointer } from "./pointer";
import { recordOf } from "./shape";

// Данные манифеста для правки: файл от каталога версии, его данные и ETag в модели версии, и
// короткое «где»: слот, пункт или документ, чтобы лента правок называла запись, а не указатель.

const DOC_FILE = /^files\/([^/]+)\/doc\.yaml$/;

/** Данные манифеста как их отдаёт модель версии; `undefined`, если файла в модели нет. */
export const dataOf = (
  model: PackVersionModel | undefined,
  file: string,
): unknown => {
  if (!model) return undefined;
  if (file === "version.yaml") return model.manifest.data;
  const id = DOC_FILE.exec(file)?.[1];
  return model.documents.find((doc) => doc.id === id)?.manifest?.data;
};

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

/** Короткое место записи: `документ / слот`, `документ` или id документа манифеста. */
export const placeOf = (
  file: string,
  pointer: string,
  data: unknown,
): string => {
  const doc = DOC_FILE.exec(file)?.[1];
  if (doc) return doc;
  const record = recordOf(pointer);
  if (record) {
    const value = resolvePointer(data, record.pointer)?.value;
    const entry =
      typeof value === "object" && value !== null
        ? (value as Record<string, unknown>)
        : {};
    const parts =
      record.kind === "slot"
        ? [str(entry.doc_id), str(entry.slot_id)]
        : record.kind === "item"
          ? [str(entry.doc_id)]
          : [str(entry.source)];
    return parts.filter(Boolean).join(" / ");
  }
  const field = /^\/forms\/\d+\/sections\/\d+\/fields\/\d+\//.exec(pointer);
  if (field) {
    const value = resolvePointer(
      data,
      pointer.slice(0, pointer.lastIndexOf("/")),
    )?.value;
    return str((value as Record<string, unknown> | undefined)?.id);
  }
  return "";
};
