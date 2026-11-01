import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { History } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatFileSize, localeTag } from "@shared/lib";
import { Badge, DataTable, Section } from "@shared/ui";
import type { BackupRun, BackupRunPage } from "../api/schemas";
import { RUNS_PAGE_SIZE } from "../api/queries";
import { durationParts } from "../lib/format";

const TONE = {
  running: "info",
  ok: "success",
  failed: "error",
  interrupted: "warning",
} as const;

export type RunsTableProps = {
  page: BackupRunPage | undefined;
  pageIndex: number;
  loading: boolean;
  error: boolean;
  onPage: (page: number) => void;
  onRetry: () => void;
};

export const RunsTable = ({
  page,
  pageIndex,
  loading,
  error,
  onPage,
  onRetry,
}: RunsTableProps) => {
  const { t } = useTranslation("adminBackups");
  const columns = useMemo<ColumnDef<BackupRun>[]>(() => {
    const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
    const duration = (seconds: number | null) => {
      if (seconds === null) return "—";
      const { h, m, s } = durationParts(seconds);
      return [
        h ? `${String(h)} ${t("units.h")}` : "",
        m ? `${String(m)} ${t("units.min")}` : "",
        `${String(s)} ${t("units.s")}`,
      ]
        .filter(Boolean)
        .join(" ");
    };
    return [
      {
        id: "started",
        header: t("runs.cols.started"),
        enableSorting: false,
        cell: ({ row }) => when(row.original.started_at),
      },
      {
        id: "status",
        header: t("runs.cols.status"),
        enableSorting: false,
        cell: ({ row }) => (
          <span
            data-testid={`backup-run-${row.original.id}`}
            data-status={row.original.status}
          >
            <Badge variant={TONE[row.original.status]}>
              {t(`runs.status.${row.original.status}`)}
              {row.original.stage
                ? ` · ${t(`runs.stage.${row.original.stage}`, { defaultValue: row.original.stage })}`
                : ""}
            </Badge>
          </span>
        ),
      },
      {
        id: "trigger",
        header: t("runs.cols.trigger"),
        enableSorting: false,
        cell: ({ row }) => t(`runs.trigger.${row.original.trigger}`),
      },
      {
        id: "destination",
        header: t("runs.cols.destination"),
        enableSorting: false,
        cell: ({ row }) => row.original.destination_name,
      },
      {
        id: "size",
        header: t("runs.cols.size"),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.size_bytes === null
            ? "—"
            : formatFileSize(row.original.size_bytes),
      },
      {
        id: "duration",
        header: t("runs.cols.duration"),
        enableSorting: false,
        cell: ({ row }) => duration(row.original.duration_s),
      },
      {
        id: "result",
        header: t("runs.cols.result"),
        enableSorting: false,
        cell: ({ row }) => {
          const run = row.original;
          if (run.error)
            return <span style={{ color: "var(--c-err)" }}>{run.error}</span>;
          if (run.removed_at)
            return <span className="dim">{t("runs.removed")}</span>;
          return run.backup_id ? <code>{run.backup_id}</code> : "—";
        },
      },
    ];
  }, [t]);

  return (
    <Section
      title={t("runs.title")}
      description={t("runs.lead")}
      flush
      testId="backup-runs"
    >
      <DataTable
        caption={t("runs.title")}
        columns={columns}
        data={page?.items ?? []}
        getRowId={(r) => r.id}
        loading={loading}
        error={error ? t("runs.loadFailed") : null}
        onRetry={onRetry}
        emptyTitle={t("runs.empty")}
        emptyHint={t("runs.emptyHint")}
        emptyIcon={<History size={18} />}
        pagination={{
          page: pageIndex,
          pageSize: RUNS_PAGE_SIZE,
          total: page?.total ?? 0,
          onPageChange: onPage,
        }}
      />
    </Section>
  );
};
