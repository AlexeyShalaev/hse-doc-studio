import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Badge, Modal, PersonCell, StatusDot } from "@shared/ui";
import type { AdminJob } from "@entities/session";
import { dateTime, formatDuration } from "../lib/format";
import { JOB_TONE, runSeconds } from "../lib/jobs";
import { shortRef, type PersonRef } from "../lib/people";
import { useDurationUnits } from "../lib/useDurationUnits";

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <>
    <dt>{label}</dt>
    <dd style={{ whiteSpace: "normal", overflowWrap: "anywhere" }}>
      {children}
    </dd>
  </>
);

/** Метаданные задачи: ошибка, раннер, попытки. Логи и результаты здесь не показываются. */
export const JobDetail = ({
  job,
  person = null,
  runnerName = null,
  now,
  onClose,
}: {
  job: AdminJob | null;
  /** Кто запустил: имя и почта, если человек найден. */
  person?: PersonRef | null;
  runnerName?: string | null;
  now: number;
  onClose: () => void;
}) => {
  const { t, i18n } = useTranslation("adminOps");
  const units = useDurationUnits();
  const locale = i18n.language;
  const run = job ? runSeconds(job, now) : null;
  return (
    <Modal
      isOpen={job !== null}
      onClose={onClose}
      title={job ? t(`queue.kind.${job.kind}`, { defaultValue: job.kind }) : ""}
      description={
        job
          ? t("queue.detail.lead", {
              when: formatPastTime(job.created_at, now),
            })
          : undefined
      }
      width={540}
    >
      {job && (
        <dl className="adm-kv" data-testid="job-detail">
          <Row label={t("queue.detail.status")}>
            <StatusDot
              status={JOB_TONE[job.status]}
              label={t(`queue.status.${job.status}`)}
            />
          </Row>
          {job.error !== null && (
            <Row label={t("queue.detail.error")}>
              <span
                data-testid="job-error"
                className="flex flex-col"
                style={{ gap: 2, alignItems: "flex-end" }}
              >
                <span style={{ color: "var(--c-err)" }}>
                  {t(`queue.errors.${job.error}`, {
                    defaultValue: t("queue.errors.unknown"),
                  })}
                </span>
                <span className="ops-code">{job.error}</span>
              </span>
            </Row>
          )}
          <Row label={t("queue.detail.user")}>
            <span
              style={{ display: "inline-flex", justifyContent: "flex-end" }}
            >
              <PersonCell
                size="sm"
                id={person?.id ?? job.user_id}
                name={person?.name ?? (job.user_name || null)}
                email={person?.email ?? null}
                fallback={t("queue.unknownPerson")}
              />
            </span>
          </Row>
          <Row label={t("queue.detail.project")}>
            {job.project_id === null
              ? t("queue.noProject")
              : (job.project_name ?? (
                  <span className="ops-code" title={job.project_id}>
                    {shortRef(job.project_id)}
                  </span>
                ))}
          </Row>
          <Row label={t("queue.detail.priority")}>
            {t(`queue.priority.${job.priority}`, {
              defaultValue: job.priority,
            })}
          </Row>
          <Row label={t("queue.detail.runner")}>
            {runnerName ?? job.runner_name ?? (
              <span className="ops-muted">{t("queue.detail.noRunner")}</span>
            )}
          </Row>
          <Row label={t("queue.detail.attempts")}>
            {t("queue.detail.attemptsValue", {
              attempt: job.attempt,
              max: job.max_attempts,
            })}
          </Row>
          {job.tags.length > 0 && (
            <Row label={t("queue.detail.tags")}>
              <span className="ops-tags" style={{ justifyContent: "flex-end" }}>
                {job.tags.map((tag) => (
                  <Badge key={tag} variant="subtle">
                    {tag}
                  </Badge>
                ))}
              </span>
            </Row>
          )}
          <Row label={t("queue.detail.created")}>
            {dateTime(job.created_at, locale)}
          </Row>
          <Row label={t("queue.detail.wait")}>
            {formatDuration(job.wait_s, units)}
          </Row>
          <Row label={t("queue.detail.run")}>
            {run === null ? (
              <span className="ops-muted">{t("queue.notStarted")}</span>
            ) : (
              formatDuration(run, units)
            )}
          </Row>
        </dl>
      )}
    </Modal>
  );
};
