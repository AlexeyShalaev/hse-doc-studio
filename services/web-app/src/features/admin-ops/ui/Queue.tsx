import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import type { AdminJob } from "@entities/session";
import type { QueueQuery } from "../api/opsApi";
import { useCancelJob, useQueue, useQueueSummary } from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { useNow } from "../lib/useNow";
import { JobDetail } from "./JobDetail";
import { PAGE_STEP, QueueView } from "./QueueView";
import { ConfirmDialog } from "./RunnerDialogs";

const statusOf = (q: { isError: boolean; isPending: boolean }) =>
  q.isError ? "error" : q.isPending ? "loading" : "ready";

/** Очередь: опрос раз в несколько секунд, отмена с подтверждением, подробности задачи. */
export const Queue = () => {
  const { t } = useTranslation("adminOps");
  const [query, setQuery] = useState<QueueQuery>({
    status: "",
    kind: "",
    q: "",
    limit: PAGE_STEP,
  });
  const jobs = useQueue(query);
  const summary = useQueueSummary();
  const cancel = useCancelJob();
  const now = useNow(5000);

  const [opened, setOpened] = useState<AdminJob | null>(null);
  const [cancelling, setCancelling] = useState<AdminJob | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  // Открытую задачу берём из свежего ответа, чтобы статус в панели не отставал.
  const fresh = opened
    ? (jobs.data?.items.find((j) => j.id === opened.id) ?? opened)
    : null;

  return (
    <>
      <QueueView
        summaryStatus={statusOf(summary)}
        summary={summary.data ?? null}
        status={statusOf(jobs)}
        jobs={jobs.data?.items ?? []}
        hasMore={jobs.data?.hasMore ?? false}
        query={query}
        now={now}
        onQueryChange={(patch) => {
          setQuery((prev) => ({ ...prev, ...patch, limit: PAGE_STEP }));
        }}
        onLoadMore={() => {
          setQuery((prev) => ({ ...prev, limit: prev.limit + PAGE_STEP }));
        }}
        onOpen={setOpened}
        onCancel={(job) => {
          setFailure(null);
          setCancelling(job);
        }}
        onRetry={() => void jobs.refetch()}
      />
      <JobDetail
        job={fresh}
        now={now}
        onClose={() => {
          setOpened(null);
        }}
      />
      <ConfirmDialog
        isOpen={cancelling !== null}
        title={t("queue.cancelDialog.title")}
        body={
          <>
            <p style={{ margin: 0 }}>
              {t("queue.cancelDialog.body", {
                user: cancelling?.user_name ?? "",
                kind: cancelling
                  ? t(`queue.kind.${cancelling.kind}`, {
                      defaultValue: cancelling.kind,
                    })
                  : "",
              })}
            </p>
            {cancelling?.status === "running" && (
              <p style={{ margin: "8px 0 0", color: "var(--fg-2)" }}>
                {t("queue.cancelDialog.running")}
              </p>
            )}
          </>
        }
        confirmLabel={t("queue.cancelDialog.confirm")}
        danger
        pending={cancel.isPending}
        failure={failure}
        testId="cancel-dialog"
        onClose={() => {
          setCancelling(null);
          setFailure(null);
        }}
        onConfirm={() => {
          if (!cancelling) return;
          setFailure(null);
          cancel.mutate(cancelling.id, {
            onSuccess: () => {
              setCancelling(null);
            },
            onError: (error) => {
              setFailure({ code: failureCode(error) });
            },
          });
        }}
      />
    </>
  );
};
