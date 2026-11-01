import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { History } from "lucide-react";
import { useTranslation } from "react-i18next";
import { localeTag } from "@shared/lib";
import { Badge, Button, DataTable, Section } from "@shared/ui";
import type { RunStatus, UpdateRun, UpdateRunPage } from "../api/schemas";
import { RUNS_PAGE_SIZE } from "../api/queries";

const TONE: Record<RunStatus, "info" | "success" | "error" | "warning"> = {
  waiting_backup: "info",
  queued: "info",
  running: "info",
  succeeded: "success",
  rolled_back: "warning",
  failed: "error",
  cancelled: "warning",
};

export type HistoryTableProps = {
  page: UpdateRunPage | undefined;
  pageIndex: number;
  loading: boolean;
  error: boolean;
  onPage: (page: number) => void;
  onRetry: () => void;
  onOpen: (run: UpdateRun) => void;
};

/** История обновлений и откатов: что, когда, чем кончилось. */
export const HistoryTable = ({
  page,
  pageIndex,
  loading,
  error,
  onPage,
  onRetry,
  onOpen,
}: HistoryTableProps) => {
  const { t } = useTranslation("adminUpdates");
  const columns = useMemo<ColumnDef<UpdateRun>[]>(() => {
    const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
    return [
      {
        id: "created",
        header: t("history.cols.created"),
        enableSorting: false,
        cell: ({ row }) => when(row.original.created_at),
      },
      {
        id: "kind",
        header: t("history.cols.kind"),
        enableSorting: false,
        cell: ({ row }) =>
          `${t(`history.kind.${row.original.kind}`)} · ${t(`history.trigger.${row.original.trigger}`)}`,
      },
      {
        id: "versions",
        header: t("history.cols.versions"),
        enableSorting: false,
        cell: ({ row }) => (
          <code>{`${row.original.from_version} → ${row.original.to_version}`}</code>
        ),
      },
      {
        id: "status",
        header: t("history.cols.status"),
        enableSorting: false,
        cell: ({ row }) => (
          <span
            data-testid={`update-run-${row.original.id}`}
            data-status={row.original.status}
          >
            <Badge variant={TONE[row.original.status]}>
              {t(`history.status.${row.original.status}`)}
            </Badge>
          </span>
        ),
      },
      {
        id: "result",
        header: t("history.cols.result"),
        enableSorting: false,
        cell: ({ row }) => {
          const run = row.original;
          const parts: string[] = [];
          if (run.db_restored) parts.push(t("history.dbRestored"));
          if (run.error) parts.push(run.error);
          return parts.length ? (
            <span
              style={{
                color: run.status === "succeeded" ? undefined : "var(--c-err)",
              }}
            >
              {parts.join(" · ")}
            </span>
          ) : (
            "—"
          );
        },
      },
      {
        id: "details",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="ghost"
            data-testid={`update-run-open-${row.original.id}`}
            onClick={() => {
              onOpen(row.original);
            }}
          >
            {t("history.details")}
          </Button>
        ),
      },
    ];
  }, [t, onOpen]);

  return (
    <Section
      title={t("history.title")}
      description={t("history.lead")}
      flush
      testId="update-history"
    >
      <DataTable
        caption={t("history.title")}
        columns={columns}
        data={page?.items ?? []}
        getRowId={(r) => r.id}
        loading={loading}
        error={error ? t("history.loadFailed") : null}
        onRetry={onRetry}
        emptyTitle={t("history.empty")}
        emptyHint={t("history.emptyHint")}
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
