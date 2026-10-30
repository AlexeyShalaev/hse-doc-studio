import type {
  AdminJob,
  AdminJobPage,
  AdminJobPageSchema,
  AdminQueueSummary,
  AdminQueueSummarySchema,
  AdminQuotas,
  AdminQuotasSchema,
  AdminService,
  AdminServiceHealthSchema,
  AdminStorage,
  AdminStorageUsageSchema,
} from "@entities/session";
import type { z } from "zod";

// Сервер отдаёт очередь, квоты, сервисы и место в формах api/schemas/admin_ops.py. Экранам нужны
// имена вместо идентификаторов и готовые числа, поэтому ответы пересобираются здесь.

type WireJobPage = z.infer<typeof AdminJobPageSchema>;
type WireJob = WireJobPage["items"][number];
type WireSummary = z.infer<typeof AdminQueueSummarySchema>;
type WireQuotas = z.infer<typeof AdminQuotasSchema>;
type WireService = z.infer<typeof AdminServiceHealthSchema>;
type WireStorage = z.infer<typeof AdminStorageUsageSchema>;

const seconds = (from: string, to: number): number =>
  Math.max(0, Math.round((to - Date.parse(from)) / 1000));

export const jobFromWire = (job: WireJob, now: number): AdminJob => ({
  id: job.id,
  kind: job.kind,
  status: job.state,
  priority: job.priority_class,
  project_id: job.project_id,
  // Подписи сервер берёт соединением; null значит, что записи уже нет.
  project_name: job.project_name,
  user_id: job.user_id,
  user_name: job.user_name ?? "",
  tags: job.tags,
  runner_id: job.runner_id,
  runner_name: job.runner_name,
  attempt: job.attempt,
  max_attempts: job.max_attempts,
  created_at: job.queued_at,
  started_at: job.started_at,
  finished_at: job.finished_at,
  wait_s: seconds(job.queued_at, Date.parse(job.started_at ?? "") || now),
  error: job.error_code,
});

export const jobPageFromWire = (
  page: WireJobPage,
  now: number,
): AdminJobPage => ({
  items: page.items.map((job) => jobFromWire(job, now)),
  hasMore: page.next_cursor !== null,
});

export const summaryFromWire = (
  summary: WireSummary,
  now: number,
): AdminQueueSummary => ({
  queued: summary.by_state.queued ?? 0,
  running: summary.by_state.running ?? 0,
  by_state: {
    queued: summary.by_state.queued ?? 0,
    running: summary.by_state.running ?? 0,
    succeeded: summary.by_state.succeeded ?? 0,
    failed: summary.by_state.failed ?? 0,
    cancelled: summary.by_state.cancelled ?? 0,
    timed_out: summary.by_state.timed_out ?? 0,
  },
  oldest_queued_age_s:
    summary.oldest_queued_at === null
      ? null
      : seconds(summary.oldest_queued_at, now),
  wait_p50_s:
    summary.wait_p50_s === null ? null : Math.round(summary.wait_p50_s),
  wait_p95_s:
    summary.wait_p95_s === null ? null : Math.round(summary.wait_p95_s),
  classes: Object.entries(summary.queued_by_class).map(([name, queued]) => ({
    name,
    queued,
  })),
});

export const quotasFromWire = (quotas: WireQuotas): AdminQuotas => ({
  user_concurrent: quotas.user_concurrent,
  org_concurrent: quotas.org_concurrent,
  max_duration_s: quotas.max_duration_s,
});

const SERVICE_KIND: Record<string, AdminService["kind"]> = {
  database: "database",
  s3: "storage",
  languagetool: "languagetool",
  onlyoffice: "onlyoffice",
  runners: "runners",
  smtp: "smtp",
};

export const serviceFromWire = (service: WireService): AdminService | null => {
  const kind = SERVICE_KIND[service.id];
  if (!kind) return null;
  return {
    id: service.id,
    kind,
    status: service.state === "not_configured" ? "unconfigured" : service.state,
    detail: service.reason,
    online: service.online,
    total: service.total,
  };
};

export const storageFromWire = (storage: WireStorage): AdminStorage => ({
  blob_count: storage.blob_count,
  blob_bytes: storage.blob_bytes,
  projects: storage.projects,
  deleted_projects: storage.deleted_projects,
  free_bytes: storage.volume_free_bytes,
  volume_total_bytes: storage.volume_total_bytes,
  computed_at: storage.computed_at,
  owners: storage.top_owners.map((owner) => ({
    id: owner.owner_id,
    name: owner.owner_name,
    projects: owner.projects,
  })),
});
