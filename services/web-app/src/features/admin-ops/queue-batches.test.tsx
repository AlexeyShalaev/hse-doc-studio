import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { adminClient } from "@shared/api";
import { i18n } from "@shared/lib";
import type { AdminJob, AdminJobBatch } from "@entities/session";
import { opsApi } from "./api/opsApi";
import { jobFromWire } from "./api/wire";
import { batchActive, batchTone, groupQueue } from "./lib/batches";
import { useQueueListState } from "./lib/lists";
import { ensureAdminOpsLocales } from "./lib/locales";
import { QueueView, type QueueViewProps } from "./ui/QueueView";

// Пакет «Собрать все» в очереди админки: одна строка группы с раскрытием до задач.

const NOW = Date.parse("2026-11-09T10:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

const BATCH: AdminJobBatch = {
  id: "b1",
  total: 3,
  by_state: { queued: 1, running: 1, succeeded: 1 },
  created_at: ago(300),
};

const job = (
  id: string,
  status: AdminJob["status"],
  extra: Partial<AdminJob> = {},
): AdminJob => ({
  id,
  kind: "compile",
  status,
  priority: "interactive",
  project_id: "p1",
  project_name: "Bertie: курсовая",
  user_id: "u1",
  user_name: "Анна Петрова",
  tags: ["tex"],
  runner_id: null,
  runner_name: null,
  attempt: 0,
  max_attempts: 3,
  created_at: ago(60),
  started_at: null,
  finished_at: null,
  wait_s: 12,
  error: null,
  ...extra,
});

const inBatch = (
  id: string,
  status: AdminJob["status"],
  batch = BATCH,
): AdminJob => job(id, status, { batch_id: batch.id, batch });

const Harness = (props: Partial<QueueViewProps> & { jobs: AdminJob[] }) => {
  const state = useQueueListState();
  return (
    <>
      <QueueView
        summaryStatus="ready"
        summary={null}
        status="ready"
        state={state}
        pagination={{
          mode: "cursor",
          shown: props.jobs.length,
          hasMore: false,
          onLoadMore: () => undefined,
          loading: false,
          totalEstimate: null,
        }}
        now={NOW}
        onOpen={() => undefined}
        onCancel={() => undefined}
        {...props}
      />
      <span data-testid="batch-filter">{state.filter("batch_id")}</span>
    </>
  );
};

const mount = (props: Partial<QueueViewProps> & { jobs: AdminJob[] }) =>
  render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <Harness {...props} />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );

describe("groupQueue", () => {
  it("collects batch jobs into one entry at the newest one, singles stay", () => {
    const jobs = [
      inBatch("a", "queued"),
      job("solo", "running"),
      inBatch("b", "running"),
    ];

    const entries = groupQueue(jobs);

    expect(entries.map((e) => e.type)).toEqual(["batch", "job"]);
    const head = entries[0];
    expect(head?.type === "batch" && head.jobs.map((j) => j.id)).toEqual([
      "a",
      "b",
    ]);
  });

  it("a batch of one document is shown as a single job", () => {
    const one: AdminJobBatch = { ...BATCH, id: "b2", total: 1 };
    expect(groupQueue([inBatch("a", "queued", one)])[0]?.type).toBe("job");
  });

  it("active jobs and the dot tone come from the whole batch", () => {
    expect(batchActive(BATCH)).toBe(2);
    expect(batchTone(BATCH)).toBe("running");
    expect(batchTone({ ...BATCH, by_state: { succeeded: 2, failed: 1 } })).toBe(
      "failed",
    );
  });
});

describe("пакет на проводе", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("the server batch summary becomes the screen batch", () => {
    const wire = {
      id: "a",
      kind: "compile" as const,
      state: "queued" as const,
      project_id: "p1",
      user_id: "u1",
      org_id: null,
      tags: ["tex"],
      priority_class: "interactive",
      queued_at: ago(60),
      started_at: null,
      finished_at: null,
      attempt: 0,
      max_attempts: 3,
      runner_id: null,
      cancel_requested: false,
      error_code: null,
      user_name: "Анна Петрова",
      user_email: null,
      org_name: null,
      project_name: "Bertie: курсовая",
      runner_name: null,
      route: "shared" as const,
      runner_scope: null,
      route_reason: null,
      batch_id: "b1",
      batch: {
        id: "b1",
        total: 2,
        by_state: { queued: 2 },
        queued_at: ago(300),
      },
    };

    const mapped = jobFromWire(wire, NOW);

    expect(mapped.batch_id).toBe("b1");
    expect(mapped.batch?.created_at).toBe(ago(300));
    expect(mapped.batch?.by_state.queued).toBe(2);
    expect(mapped.batch?.by_state.running).toBe(0);
  });

  it("cancel all posts to the batch route and returns the count", async () => {
    const post = vi
      .spyOn(adminClient, "post")
      .mockResolvedValue({ data: { cancelled: 3 } });

    expect(await opsApi.cancelJobBatch("b1")).toBe(3);
    expect(post.mock.calls[0]?.[0]).toBe("/queue/batches/b1/cancel");
  });
});

describe("QueueView: пакеты «Собрать все»", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
    await ensureAdminOpsLocales();
  });
  afterEach(cleanup);

  it("one group row with project, person, count and states; jobs hidden until expanded", async () => {
    const user = userEvent.setup();
    mount({
      jobs: [
        inBatch("a", "queued"),
        job("solo", "running"),
        inBatch("b", "running"),
      ],
    });

    const group = screen.getByTestId("queue-batch-b1");
    expect(group).toHaveTextContent("Сборка всех документов");
    expect(group).toHaveTextContent("3 задачи");
    expect(group).toHaveTextContent("Bertie: курсовая");
    expect(screen.getByTestId("batch-status-b1")).toHaveTextContent(
      "В очереди: 1 · Выполняется: 1 · Готово: 1",
    );
    expect(screen.getByTestId("batch-when-b1")).toHaveTextContent("назад");
    expect(screen.getByTestId("job-status-solo")).toBeInTheDocument();
    expect(screen.queryByTestId("job-status-a")).toBeNull();

    await user.click(screen.getByTestId("queue-batch-toggle-b1"));

    expect(screen.getByTestId("job-status-a")).toBeInTheDocument();
    expect(screen.getByTestId("job-status-b")).toBeInTheDocument();
    // На экране две задачи из трёх: ссылка открывает весь пакет фильтром.
    await user.click(screen.getByTestId("queue-batch-all-b1"));
    expect(screen.getByTestId("batch-filter")).toHaveTextContent("b1");
  });

  it("cancel all asks with the batch and its first job", async () => {
    const user = userEvent.setup();
    const onCancelBatch =
      vi.fn<(batch: AdminJobBatch, lead: AdminJob) => void>();
    mount({
      jobs: [inBatch("a", "queued"), inBatch("b", "running")],
      onCancelBatch,
    });

    await user.click(screen.getByTestId("batch-cancel-b1"));

    expect(onCancelBatch).toHaveBeenCalledOnce();
    const [batch, lead] = onCancelBatch.mock.calls[0] ?? [];
    expect(batch?.id).toBe("b1");
    expect(lead?.id).toBe("a");
  });

  it("a finished batch has no cancel button", () => {
    const done: AdminJobBatch = {
      ...BATCH,
      by_state: { succeeded: 2, failed: 1 },
    };
    mount({
      jobs: [inBatch("a", "succeeded", done), inBatch("b", "failed", done)],
    });

    const group = screen.getByTestId("queue-batch-b1").closest("tr");
    expect(group).not.toBeNull();
    expect(
      within(group as HTMLElement).queryByRole("button", {
        name: /Отменить все/,
      }),
    ).toBeNull();
    expect(screen.queryByTestId("batch-cancel-b1")).toBeNull();
  });
});
