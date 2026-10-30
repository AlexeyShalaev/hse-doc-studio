import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import type { AdminJob } from "@entities/session";
import type { QueueQuery } from "../api/opsApi";
import {
  useCancelJob,
  usePeople,
  useQueue,
  useQueueSummary,
  usePersonalRunners,
  useRunners,
} from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { personRef } from "../lib/people";
import { useNow } from "../lib/useNow";
import { JobDetail } from "./JobDetail";
import { statusOf } from "../lib/viewStatus";
import { PAGE_STEP, QueueView } from "./QueueView";
import { ConfirmDialog } from "./RunnerDialogs";

const PERSONAL_RUNNING = {
  status: "running",
  kind: "",
  q: "",
  limit: 200,
  scope: "personal",
} as const;

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
  const runners = useRunners();
  const personalRunners = usePersonalRunners();
  // Сколько задач сейчас на личных раннерах: отдельной сводки сервер не отдаёт.
  const personal = useQueue(PERSONAL_RUNNING);
  const cancel = useCancelJob();
  const now = useNow(5000);

  const items = jobs.data?.items;
  const ids = useMemo(() => (items ?? []).map((j) => j.user_id), [items]);
  const people = usePeople(ids);
  const runnerNames = useMemo(
    () =>
      new Map(
        [...(runners.data ?? []), ...(personalRunners.data ?? [])].map((r) => [
          r.id,
          r.name,
        ]),
      ),
    [runners.data, personalRunners.data],
  );
  // Сервер без личных раннеров не знает runner_scope: плитку не показываем.
  const knowsScope = (items ?? []).some((j) => j.runner_scope !== undefined);

  const [opened, setOpened] = useState<AdminJob | null>(null);
  const [cancelling, setCancelling] = useState<AdminJob | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  // Открытую задачу берём из свежего ответа, чтобы статус в панели не отставал.
  const fresh = opened
    ? (items?.find((j) => j.id === opened.id) ?? opened)
    : null;
  const cancellingWho = cancelling
    ? personRef(cancelling.user_id, cancelling.user_name, people)
    : null;

  return (
    <>
      <QueueView
        summaryStatus={statusOf(summary)}
        summary={summary.data ?? null}
        status={statusOf(jobs)}
        jobs={items ?? []}
        hasMore={jobs.data?.hasMore ?? false}
        people={people}
        runnerNames={runnerNames}
        personalRunning={
          knowsScope ? (personal.data?.items.length ?? null) : undefined
        }
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
        person={
          fresh ? personRef(fresh.user_id, fresh.user_name, people) : null
        }
        runnerName={
          fresh?.runner_id
            ? (runnerNames.get(fresh.runner_id) ?? fresh.runner_name)
            : null
        }
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
