import { useTranslation } from "react-i18next";
import { Download, FolderOpen, Inbox, Package } from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { submissionApi, useSubmissions } from "@entities/submission";
import { useCapabilities } from "@entities/session";
import { useEditors } from "@entities/system";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag, toast } from "@shared/lib";
import { OpenInEditorMenu } from "./OpenInEditorMenu";

type Project = z.infer<typeof ProjectResponseSchema>;

export type CheckpointBuildsProps = {
  project: Project;
  /** Показываем сборки ТОЛЬКО этой точки — экран отвечает за неё одну. */
  profileId: string;
};

const formatBytes = (bytes: number | null | undefined): string => {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${String(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const formatDate = (iso: string): string =>
  new Date(iso).toLocaleString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

export const CheckpointBuilds = ({
  project,
  profileId,
}: CheckpointBuildsProps) => {
  const { t } = useTranslation("workspace");
  const { data: submissions, isLoading } = useSubmissions(project.id);
  const { data: editorsData } = useEditors();
  const { lacks } = useCapabilities();
  const availableEditors = (editorsData?.editors ?? []).filter(
    (e) => e.available,
  );

  // Колонки «профиль» здесь нет намеренно: все строки — одной точки, и чип с её
  // названием повторял бы заголовок экрана в каждой строке.
  const builds = (submissions ?? []).filter((s) => s.profile_id === profileId);

  return (
    <div style={{ marginTop: "1.75rem" }}>
      <h3
        className="mono dim"
        style={{
          margin: "0 0 0.875rem",
          fontSize: "0.65625rem",
          textTransform: "uppercase",
          letterSpacing: "0.12em",
        }}
      >
        {t("pack.pastBuilds")}
      </h3>
      <div className="card">
        {isLoading ? (
          <div style={{ padding: "1.125rem", textAlign: "center" }}>
            <Spinner size="sm" />
          </div>
        ) : builds.length === 0 ? (
          <div
            className="flex items-center justify-center"
            style={{
              gap: "0.5rem",
              padding: "1.75rem",
              color: "var(--fg-3)",
              fontSize: "0.75rem",
            }}
          >
            <Inbox size="0.875rem" />
            {t("pack.noSubmissions")}
          </div>
        ) : (
          builds.map((s, i) => (
            <div
              key={s.id}
              className="flex items-center"
              style={{
                padding: "0.625rem 1rem",
                borderBottom:
                  i < builds.length - 1 ? "1px solid var(--border)" : 0,
                gap: "0.75rem",
              }}
            >
              <Package size="0.8125rem" style={{ color: "var(--fg-3)" }} />
              <span
                className="mono"
                style={{
                  fontSize: "0.71875rem",
                  color: "var(--fg-0)",
                  width: "7.25rem",
                }}
              >
                {formatDate(s.created_at)}
              </span>
              {s.archive_format && (
                <span
                  className="chip mono"
                  style={{ fontSize: "0.625rem", textTransform: "uppercase" }}
                  title={t("pack.archiveFormatTitle")}
                >
                  {s.archive_format}
                </span>
              )}
              <span className="dim" style={{ fontSize: "0.6875rem" }}>
                {t("pack.docCount", { count: s.doc_count ?? 0 })}
              </span>
              <span
                className="flex-1 mono dim truncate"
                style={{ fontSize: "0.6875rem" }}
                title={s.output_path ?? ""}
              >
                {s.output_path ?? "—"}
              </span>
              <span
                className="mono dim shrink-0"
                style={{
                  fontSize: "0.65625rem",
                  width: "4.25rem",
                  textAlign: "right",
                }}
              >
                {formatBytes(s.size_bytes)}
              </span>
              {!lacks("open_in_editor") && (
                <OpenInEditorMenu
                  outputDir={s.output_dir}
                  editors={availableEditors}
                />
              )}
              {s.output_path && (
                <a
                  href={submissionApi.downloadUrl(project.id, s.id)}
                  className="icon-btn sm tt"
                  data-tt={t("pack.download")}
                  download
                >
                  <Download size="0.6875rem" />
                </a>
              )}
              <button
                type="button"
                className="icon-btn sm tt"
                data-tt={t("pack.copyPath")}
                onClick={() => {
                  if (s.output_path) {
                    navigator.clipboard
                      .writeText(s.output_path)
                      .then(() => {
                        toast.info(t("pack.pathCopied"));
                      })
                      .catch(() => {
                        /* clipboard blocked */
                      });
                  }
                }}
              >
                <FolderOpen size="0.6875rem" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
