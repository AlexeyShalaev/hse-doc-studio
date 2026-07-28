import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Inbox } from "lucide-react";
import { clsx } from "clsx";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useQueries } from "@tanstack/react-query";
import { useProjects } from "@entities/project";
import { changelogApi, changelogKeys } from "@entities/changelog";
import { localeTag } from "@shared/lib";
import type { ChangeLogEntryResponse, ChangeLogKind } from "@shared/api/types";

type Severity = "ok" | "warn" | "err" | "info";

const KIND_SEVERITY: Record<ChangeLogKind, Severity> = {
  compile_ok: "ok",
  compile_fail: "err",
  edit: "info",
  manual_note: "info",
  sign: "ok",
  pack_submission: "info",
};

const KIND_LABEL_KEY: Record<ChangeLogKind, string> = {
  compile_ok: "activity.kind.compileOk",
  compile_fail: "activity.kind.compileFail",
  edit: "activity.kind.edit",
  manual_note: "activity.kind.manualNote",
  sign: "activity.kind.sign",
  pack_submission: "activity.kind.packSubmission",
};

type EnrichedEvent = ChangeLogEntryResponse & {
  project: { id: string; name: string };
};

const MS_PER_MINUTE = 60_000;

export const RecentActivity = () => {
  const { t } = useTranslation("welcome");
  const navigate = useNavigate();
  const { data: projects } = useProjects();

  // The "N minutes ago" labels need the wall clock, but reading it while
  // rendering is impure. Snapshot it in state instead and re-tick once a
  // minute, so the labels keep ageing on a long-open page.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, MS_PER_MINUTE);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const formatTimeAgo = (iso: string): string => {
    const then = new Date(iso).getTime();
    const diffMin = Math.floor((now - then) / MS_PER_MINUTE);
    if (diffMin < 1) return t("activity.time.justNow");
    if (diffMin < 60) return t("activity.time.minutesAgo", { count: diffMin });
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return t("activity.time.hoursAgo", { count: diffH });
    const diffD = Math.floor(diffH / 24);
    if (diffD < 30) return t("activity.time.daysAgo", { count: diffD });
    return new Date(iso).toLocaleDateString(localeTag());
  };
  const projectList = useMemo(() => projects ?? [], [projects]);

  // Parallel per-project changelog fetches via useQueries.
  const changelogQueries = useQueries({
    queries: projectList.map((p) => ({
      queryKey: changelogKeys.list(p.id, undefined),
      queryFn: () => changelogApi.list(p.id),
      staleTime: 30_000,
    })),
  });

  const events = useMemo<EnrichedEvent[]>(() => {
    const out: EnrichedEvent[] = [];
    projectList.forEach((p, i) => {
      const entries = changelogQueries[i]?.data ?? [];
      entries.forEach((e) => {
        out.push({ ...e, project: p });
      });
    });
    out.sort((a, b) => (a.at < b.at ? 1 : -1));
    return out.slice(0, 8);
  }, [projectList, changelogQueries]);

  const isLoading =
    projectList.length > 0 && changelogQueries.some((q) => q.isLoading);

  if (projectList.length === 0) return null;

  return (
    <div style={{ marginTop: 36 }}>
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: 14 }}
      >
        <h3
          className="mono dim m-0"
          style={{
            fontSize: 10.5,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          {t("activity.title")}
        </h3>
        <span className="dim" style={{ fontSize: 11 }}>
          {t("activity.subtitle")}
        </span>
      </div>

      <div className="card">
        {isLoading && events.length === 0 ? (
          <div
            className="dim"
            style={{ padding: "24px 14px", textAlign: "center", fontSize: 12 }}
          >
            {t("activity.loading")}
          </div>
        ) : events.length === 0 ? (
          <div
            className="flex items-center justify-center"
            style={{
              gap: 8,
              padding: "28px 14px",
              color: "var(--fg-3)",
              fontSize: 12,
            }}
          >
            <Inbox size={14} />
            {t("activity.empty")}
          </div>
        ) : (
          events.map((event, i) => {
            const severity = KIND_SEVERITY[event.kind];
            return (
              <div
                key={event.id}
                role="button"
                tabIndex={0}
                className="flex items-center cursor-pointer"
                style={{
                  padding: "10px 14px",
                  borderBottom:
                    i < events.length - 1 ? "1px solid var(--border)" : "0",
                  gap: 12,
                }}
                onClick={() => {
                  void navigate(
                    event.doc_id
                      ? `/projects/${event.project.id}/documents/${event.doc_id}`
                      : `/projects/${event.project.id}/documents`,
                  );
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    void navigate(
                      event.doc_id
                        ? `/projects/${event.project.id}/documents/${event.doc_id}`
                        : `/projects/${event.project.id}/documents`,
                    );
                  }
                }}
              >
                <span className={clsx("dot", severity)} />
                <span
                  className="mono dim shrink-0"
                  style={{ fontSize: 10.5, width: 72 }}
                >
                  {formatTimeAgo(event.at)}
                </span>
                <span
                  className="chip shrink-0"
                  style={{ maxWidth: 140 }}
                  title={event.project.name}
                >
                  <span className="truncate">{event.project.name}</span>
                </span>
                {event.doc_id && (
                  <span
                    className="chip accent shrink-0 mono"
                    style={{ textTransform: "uppercase" }}
                  >
                    {event.doc_id}
                  </span>
                )}
                <span className="chip shrink-0">
                  {t(KIND_LABEL_KEY[event.kind])}
                </span>
                <span
                  className="flex-1 min-w-0 truncate"
                  style={{
                    fontSize: 12.5,
                    color: severity === "err" ? "var(--c-err)" : "var(--fg-1)",
                  }}
                  title={event.summary}
                >
                  {event.summary}
                </span>
                <ChevronRight
                  size={11}
                  style={{ color: "var(--fg-3)", flexShrink: 0 }}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
