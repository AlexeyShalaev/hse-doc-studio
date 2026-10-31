import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { useCursorList } from "@shared/lib";
import type { AdminJob } from "@entities/session";
import { opsApi } from "../api/opsApi";
import {
  opsKeys,
  POLL_MS,
  useCancelJob,
  usePersonalRunnersEnabled,
  usePersonalRunningJobs,
  useQueueSummary,
} from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { useQueueListState } from "../lib/lists";
import { personRef } from "../lib/people";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import { JobDetail } from "./JobDetail";
import { QueueView } from "./QueueView";
import { ConfirmDialog } from "./RunnerDialogs";

const jobId = (job: AdminJob) => job.id;

/**
 * Очередь: журнал по курсору сервера, «Показать ещё» дописывает страницы.
 * Опрос раз в несколько секунд перечитывает только первую страницу и вклеивает
 * её сверху; отмена с подтверждением, подробности задачи.
 */
export const Queue = () => {
  const { t } = useTranslation("adminOps");
  const state = useQueueListState();
  const jobs = useCursorList({
    state,
    queryKey: opsKeys.queueAll,
    fetchPage: (params, signal) => opsApi.queue(params, signal),
    getId: jobId,
    pollMs: POLL_MS,
  });
  const summary = useQueueSummary();
  const cancel = useCancelJob();
  const now = useNow(5000);
  // Сколько задач сейчас на личных раннерах: отдельной сводки сервер не отдаёт.
  // Плитку не показываем, пока личные раннеры выключены на установке.
  const personalEnabled = usePersonalRunnersEnabled();
  const personalRunning = usePersonalRunningJobs();

  const [opened, setOpened] = useState<AdminJob | null>(null);
  const [cancelling, setCancelling] = useState<AdminJob | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  // Открытую задачу берём из свежего ответа, чтобы статус в панели не отставал.
  const fresh = opened
    ? (jobs.items.find((j) => j.id === opened.id) ?? opened)
    : null;
  const cancellingWho = cancelling
    ? personRef(cancelling.user_id, cancelling.user_name, cancelling.user_email)
    : null;

  return (
    <>
      <QueueView
        summaryStatus={statusOf(summary)}
        summary={summary.data ?? null}
        status={statusOf(jobs.query)}
        jobs={jobs.items}
        fetching={jobs.isFetching && !jobs.isLoadingMore}
        failed={jobs.isError}
        state={state}
        pagination={jobs.pagination}
        personalRunning={
          personalEnabled.data
            ? (personalRunning.data?.length ?? null)
            : undefined
        }
        now={now}
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
                user: cancellingWho?.name ?? t("queue.unknownPerson"),
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
