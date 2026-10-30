import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, DataTable } from "@shared/ui";
import type { AdminUser } from "@entities/session";
import { PAGE_SIZE } from "../api/adminUsersApi";
import { useApprovals, useDecideApproval } from "../api/adminUsersQueries";
import type { Failure } from "../lib/failure";
import { formatDate } from "../lib/format";
import { FailureNotice, Person } from "./parts";

/** Вкладка «Одобрения»: люди, которые зарегистрировались и ждут решения администратора. */
export const ApprovalsPanel = () => {
  const { t, i18n } = useTranslation("adminUsers");
  const [page, setPage] = useState(0);
  const list = useApprovals(page);
  const decide = useDecideApproval();
  const [failure, setFailure] = useState<Failure | null>(null);

  const columns = useMemo<ColumnDef<AdminUser>[]>(
    () => [
      {
        id: "person",
        header: t("users.columns.person"),
        cell: ({ row }) => (
          <Person name={row.original.name} email={row.original.email} />
        ),
      },
      {
        id: "created",
        header: t("approvals.columns.created"),
        cell: ({ row }) => (
          <span style={{ color: "var(--fg-2)" }}>
            {formatDate(row.original.created_at, i18n.language)}
          </span>
        ),
      },
      {
        id: "actions",
        header: () => (
          <span className="sr-only">{t("users.columns.actions")}</span>
        ),
        cell: ({ row }) => {
          const u = row.original;
          const go = (approve: boolean) => () => {
            setFailure(null);
            decide.mutate(
              { id: u.id, approve },
              {
                onError: (error) => {
                  setFailure({ code: failureCode(error) });
                },
              },
            );
          };
          return (
            <div
              className="flex"
              style={{ gap: 6, justifyContent: "flex-end" }}
            >
              <Button
                size="xs"
                type="button"
                disabled={decide.isPending}
                data-testid={`approve-${u.id}`}
                aria-label={t("approvals.approveAria", { name: u.name })}
                onClick={go(true)}
              >
                <Check size={13} aria-hidden="true" />
                {t("approvals.approve")}
              </Button>
              <Button
                size="xs"
                variant="outline"
                type="button"
                disabled={decide.isPending}
                data-testid={`reject-${u.id}`}
                aria-label={t("approvals.rejectAria", { name: u.name })}
                onClick={go(false)}
              >
                <X size={13} aria-hidden="true" />
                {t("approvals.reject")}
              </Button>
            </div>
          );
        },
      },
    ],
    [t, i18n.language, decide],
  );

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="approvals-panel"
    >
      {failure && <FailureNotice failure={failure} />}
      <DataTable
        caption={t("approvals.caption")}
        columns={columns}
        data={list.data?.items ?? []}
        getRowId={(u) => u.id}
        loading={list.isPending}
        error={list.isError ? t("approvals.loadFailed") : null}
        onRetry={() => {
          void list.refetch();
        }}
        emptyTitle={t("approvals.empty.title")}
        emptyHint={t("approvals.empty.body")}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total: list.data?.total ?? 0,
          onPageChange: setPage,
        }}
      />
    </div>
  );
};
