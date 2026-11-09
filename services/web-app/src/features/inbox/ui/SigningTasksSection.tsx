import { useState } from "react";
import { FilePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib";
import { Badge, Button, EmptyState, Spinner } from "@shared/ui";
import type { SigningTaskSummary } from "@entities/signing-route";
import {
  formatDeadline,
  isOverdue,
  sortSigningTasks,
} from "../lib/signingTasks";

export type SigningTasksStatus = "loading" | "error" | "ready";

export type SigningTasksSectionProps = {
  tasks: SigningTaskSummary[];
  status: SigningTasksStatus;
  /**
   * Вкладка «На подпись»: загрузка и пустой список видны. Во вкладке «Всё» раздел появляется,
   * только когда есть задачи или они не загрузились.
   */
  standalone: boolean;
  lang: string;
  onOpen: (task: SigningTaskSummary) => void;
  onRetry: () => void;
};

const CARD = {
  padding: "0.75rem 0.875rem",
  borderRadius: "var(--r-3)",
  border: "1px solid var(--border)",
  background: "var(--bg-1)",
  display: "flex",
  alignItems: "flex-start",
  gap: "0.75rem",
} as const;

/** «На подпись» (раздел 3.2): где сейчас ждут действия человека, по всем проектам. */
export const SigningTasksSection = ({
  tasks,
  status,
  standalone,
  lang,
  onOpen,
  onRetry,
}: SigningTasksSectionProps) => {
  const { t } = useTranslation("inbox");
  const [now] = useState(() => Date.now());
  const ready = status === "ready" || tasks.length > 0;
  if (!standalone && tasks.length === 0 && status !== "error") return null;

  return (
    <section
      className="flex flex-col"
      style={{ gap: "0.5rem" }}
      aria-labelledby="inbox-signing-title"
      data-testid="inbox-signing"
    >
      <h2
        id="inbox-signing-title"
        className="flex items-center"
        style={{ margin: 0, gap: "0.375rem", fontSize: "0.875rem" }}
      >
        {t("signing.title")}
        {tasks.length > 0 && <Badge variant="accent">{tasks.length}</Badge>}
      </h2>

      {!ready && status === "loading" && (
        <div
          className="flex items-center"
          style={{
            gap: "0.5rem",
            color: "var(--fg-2)",
            fontSize: "0.78125rem",
          }}
          data-testid="inbox-signing-loading"
        >
          <Spinner size="sm" />
          {t("signing.loading")}
        </div>
      )}

      {!ready && status === "error" && (
        <div role="alert" data-testid="inbox-signing-error">
          <EmptyState
            compact
            framed
            title={t("signing.error")}
            action={
              <Button
                type="button"
                variant="secondary"
                size="sm"
                data-testid="inbox-signing-retry"
                onClick={onRetry}
              >
                {t("signing.retry")}
              </Button>
            }
          />
        </div>
      )}

      {ready && tasks.length === 0 && (
        <EmptyState
          framed
          testId="inbox-signing-empty"
          icon={<FilePen size="1.125rem" />}
          title={t("signing.empty")}
          description={t("signing.emptyHint")}
        />
      )}

      {sortSigningTasks(tasks).map((task) => {
        const name = pickLocalized(task.profile.name, lang, task.profile.id);
        const overdue = isOverdue(task.deadline, now);
        const deadline = task.deadline
          ? formatDeadline(task.deadline, now)
          : null;
        return (
          <article
            key={`${task.project.id}:${task.route_id}`}
            style={CARD}
            data-testid={`inbox-signing-task-${task.route_id}`}
            data-action={task.next_action}
            data-overdue={overdue}
          >
            <span
              aria-hidden="true"
              className="shrink-0"
              style={{ marginTop: "0.125rem", color: "var(--accent)" }}
            >
              <FilePen size="1rem" />
            </span>
            <div
              className="flex flex-col min-w-0"
              style={{ flex: 1, gap: "0.3125rem" }}
            >
              <strong
                style={{ fontSize: "0.84375rem", overflowWrap: "anywhere" }}
              >
                {name}
              </strong>
              <span
                className="dim"
                style={{ fontSize: "0.75rem", overflowWrap: "anywhere" }}
              >
                {task.project.name}
                {task.sender &&
                  ` · ${t("signing.from", { name: task.sender })}`}
              </span>
              <span
                className="flex items-center flex-wrap"
                style={{ gap: "0.5rem" }}
              >
                <Badge variant="subtle" data-testid="inbox-signing-action">
                  {t(`signing.action.${task.next_action}`)}
                </Badge>
                {deadline &&
                  (overdue ? (
                    <Badge variant="error" data-testid="inbox-signing-deadline">
                      {t("signing.overdue", { date: deadline })}
                    </Badge>
                  ) : (
                    <span
                      className="dim"
                      style={{ fontSize: "0.71875rem" }}
                      data-testid="inbox-signing-deadline"
                    >
                      {t("signing.deadline", { date: deadline })}
                    </span>
                  ))}
              </span>
            </div>
            <Button
              type="button"
              size="sm"
              className="shrink-0"
              aria-label={t("signing.openLabel", { name })}
              data-testid={`inbox-signing-open-${task.route_id}`}
              onClick={() => {
                onOpen(task);
              }}
            >
              {t("signing.open")}
            </Button>
          </article>
        );
      })}
    </section>
  );
};
