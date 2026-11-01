import type {
  BackupDestination,
  DestinationBody,
  DestinationKind,
} from "../api/schemas";

/** Готовые значения для S3 из оверлея deploy/server/compose.backup-s3.yml. */
export const OWN_S3_HINT = {
  endpoint: "http://backup-minio:9000",
  region: "us-east-1",
  bucket: "hse-backups",
  prefix: "studio",
  pathStyle: true,
} as const;

export type DestinationDraft = {
  name: string;
  kind: DestinationKind;
  endpoint: string;
  region: string;
  bucket: string;
  prefix: string;
  pathStyle: boolean;
  localPath: string;
  accessKey: string;
  secretKey: string;
  makeDefault: boolean;
};

export const emptyDraft = (firstOne: boolean): DestinationDraft => ({
  name: "",
  kind: "s3",
  endpoint: "",
  region: "us-east-1",
  bucket: "",
  prefix: "",
  pathStyle: true,
  localPath: "",
  accessKey: "",
  secretKey: "",
  makeDefault: firstOne,
});

export const draftOf = (d: BackupDestination): DestinationDraft => ({
  name: d.name,
  kind: d.kind,
  endpoint: d.endpoint ?? "",
  region: d.region,
  bucket: d.bucket ?? "",
  prefix: d.prefix,
  pathStyle: d.path_style,
  localPath: d.local_path ?? "",
  // Секреты обратно не приходят: пустое поле значит «оставить как есть».
  accessKey: "",
  secretKey: "",
  makeDefault: d.is_default,
});

export type DraftField =
  | "name"
  | "endpoint"
  | "bucket"
  | "prefix"
  | "localPath"
  | "accessKey"
  | "secretKey";

const BUCKET = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/;
const PREFIX_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._ -]*$/;

/** Первое неверное поле формы или `null`. Сервер проверяет то же самое ещё раз. */
export const draftProblem = (
  draft: DestinationDraft,
  editing: boolean,
): DraftField | null => {
  if (draft.name.trim() === "" || draft.name.trim().length > 128) return "name";
  if (draft.kind === "local") {
    const parts = draft.localPath
      .trim()
      .replaceAll("\\", "/")
      .split("/")
      .filter((p) => p !== "");
    const ok =
      parts.length > 0 &&
      parts.every((p) => p !== ".." && p !== "." && PREFIX_SEGMENT.test(p));
    return ok ? null : "localPath";
  }
  if (!BUCKET.test(draft.bucket.trim())) return "bucket";
  const endpoint = draft.endpoint.trim();
  if (endpoint !== "" && !/^https?:\/\/[^\s/@]+(:\d+)?(\/.*)?$/.test(endpoint))
    return "endpoint";
  const prefix = draft.prefix.trim().replace(/^\/+|\/+$/g, "");
  if (
    prefix !== "" &&
    !prefix.split("/").every((p) => p !== ".." && PREFIX_SEGMENT.test(p))
  )
    return "prefix";
  if (!editing && draft.accessKey.trim() === "") return "accessKey";
  if (!editing && draft.secretKey.trim() === "") return "secretKey";
  return null;
};

export const bodyFromDraft = (draft: DestinationDraft): DestinationBody => {
  const local = draft.kind === "local";
  return {
    name: draft.name.trim(),
    kind: draft.kind,
    endpoint:
      local || draft.endpoint.trim() === "" ? null : draft.endpoint.trim(),
    region: draft.region.trim() || "us-east-1",
    bucket: local ? null : draft.bucket.trim(),
    prefix: local ? "" : draft.prefix.trim(),
    path_style: draft.pathStyle,
    local_path: local ? draft.localPath.trim() : null,
    access_key:
      local || draft.accessKey.trim() === "" ? null : draft.accessKey.trim(),
    secret_key:
      local || draft.secretKey.trim() === "" ? null : draft.secretKey.trim(),
    make_default: draft.makeDefault,
  };
};

/** Подставляет значения собственного S3 из оверлея; ключи остаются как есть. */
export const withOwnS3 = (draft: DestinationDraft): DestinationDraft => ({
  ...draft,
  kind: "s3",
  endpoint: OWN_S3_HINT.endpoint,
  region: OWN_S3_HINT.region,
  bucket: OWN_S3_HINT.bucket,
  prefix: draft.prefix || OWN_S3_HINT.prefix,
  pathStyle: OWN_S3_HINT.pathStyle,
  name: draft.name || "Свой S3",
});
