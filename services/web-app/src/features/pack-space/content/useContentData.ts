import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  usePackVersionModel,
  type PackVersionModel,
} from "@entities/pack-studio";
import { useSpace } from "../context/SpaceContext";
import type { ContentDocument, ContentPart } from "./contract";
import { toContentDocuments } from "./documents";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Число записей списка или словаря (`meta_fields` это словарь «ключ: описание»). */
const lengthOf = (value: unknown): number | null =>
  Array.isArray(value)
    ? value.length
    : isRecord(value)
      ? Object.keys(value).length
      : null;

/** Числа у пунктов навигации из манифеста версии; `null`: пункту число не нужно. */
export const countsOf = (
  model: PackVersionModel,
): Partial<Record<ContentPart | "documents", number>> => {
  const data = isRecord(model.manifest.data) ? model.manifest.data : {};
  const out: Partial<Record<ContentPart | "documents", number>> = {
    documents: model.documents.length,
  };
  const put = (key: ContentPart, count: number | null) => {
    if (count !== null) out[key] = count;
  };
  put("fields", lengthOf(data.meta_fields));
  put("forms", lengthOf(data.forms));
  put(
    "deadlines",
    lengthOf(
      isRecord(data.pack_submission) ? data.pack_submission.profiles : null,
    ),
  );
  put(
    "signatures",
    lengthOf(isRecord(data.signatures) ? data.signatures.slots : null),
  );
  return out;
};

export type ContentData = {
  workspaceId: string;
  versionDir: string;
  /** Выпущенная версия или отказ сервера писать. */
  readOnly: boolean;
  status: "loading" | "error" | "ready";
  error: unknown;
  refetch: () => void;
  docs: ContentDocument[];
  counts: Partial<Record<ContentPart | "documents", number>>;
};

/**
 * Документы и числа версии для навигации и центра. Модель версии грузится один раз на экран
 * (общий кэш запросов), навигация и центр читают её независимо.
 */
export const useContentData = (): ContentData => {
  const { i18n } = useTranslation();
  const { workspace, versionRef, version, released } = useSpace();
  const versionDir =
    version?.path ??
    `${versionRef.pack}/templates/${versionRef.template}/versions/${versionRef.version}`;
  const query = usePackVersionModel(workspace.id, versionRef);
  const model = query.data;
  const lang = i18n.language;
  const docs = useMemo(
    () => (model ? toContentDocuments(model, versionDir, lang) : []),
    [model, versionDir, lang],
  );
  const counts = useMemo(() => (model ? countsOf(model) : {}), [model]);
  return {
    workspaceId: workspace.id,
    versionDir,
    readOnly: released || (model?.read_only ?? null) !== null,
    status: query.isPending ? "loading" : query.isError ? "error" : "ready",
    error: query.error,
    refetch: () => void query.refetch(),
    docs,
    counts,
  };
};
