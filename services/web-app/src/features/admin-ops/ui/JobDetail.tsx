import { useTranslation } from "react-i18next";
import { Badge, Modal } from "@shared/ui";
import type { AdminJob } from "@entities/session";
import { dateTime, formatDuration } from "../lib/format";
import { JOB_BADGE, runSeconds } from "../lib/jobs";
import { useDurationUnits } from "../lib/useDurationUnits";

const Row = ({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) => (
  <div
    className="flex"
    style={{
      gap: 12,
      fontSize: 12.5,
      padding: "5px 0",
      borderTop: "1px solid var(--border)",
    }}
  >
    <dt style={{ width: 130, flexShrink: 0, color: "var(--fg-2)" }}>{label}</dt>
    <dd style={{ margin: 0, minWidth: 0, overflowWrap: "anywhere" }}>
      {children}
    </dd>
  </div>
);

/** Метаданные задачи: ошибка, раннер, попытки. Логи и результаты здесь не показываются. */
export const JobDetail = ({
  job,
  now,
  onClose,
}: {
  job: AdminJob | null;
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
      description={job?.id}
      width={540}
    >
      {job && (
        <dl style={{ margin: 0 }} data-testid="job-detail">
          <Row label={t("queue.detail.status")}>
            <Badge variant={JOB_BADGE[job.status]}>
              {t(`queue.status.${job.status}`)}
            </Badge>
          </Row>
          <Row label={t("queue.detail.user")}>{job.user_name}</Row>
          <Row label={t("queue.detail.project")}>
            {job.project_name ?? t("queue.noProject")}
          </Row>
          <Row label={t("queue.detail.runner")}>
            {job.runner_name ?? t("queue.detail.noRunner")}
          </Row>
          <Row label={t("queue.detail.attempts")}>
            {t("queue.detail.attemptsValue", {
              attempt: job.attempt,
              max: job.max_attempts,
            })}
          </Row>
          <Row label={t("queue.detail.tags")}>
            {job.tags.length === 0 ? "-" : job.tags.join(", ")}
          </Row>
          <Row label={t("queue.detail.created")}>
            {dateTime(job.created_at, locale)}
          </Row>
          <Row label={t("queue.detail.wait")}>
            {formatDuration(job.wait_s, units)}
          </Row>
          <Row label={t("queue.detail.run")}>
            {run === null ? "-" : formatDuration(run, units)}
          </Row>
          {job.error !== null && (
            <Row label={t("queue.detail.error")}>
              <span data-testid="job-error" style={{ color: "var(--c-err)" }}>
                {job.error}
              </span>
            </Row>
          )}
        </dl>
      )}
    </Modal>
  );
};
