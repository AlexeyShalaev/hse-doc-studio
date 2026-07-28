import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bookmark, Camera, History, Undo2 } from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import {
  type VcsCommit,
  type VcsRestore,
  useCreateVcsSnapshot,
  useInitVcs,
  useRestoreVcs,
  useVcsDiff,
  useVcsHistory,
  useVcsStatus,
} from "@entities/vcs";
import {
  EMPTY_VCS_FILTERS,
  RestoreConfirmModal,
  type VcsHistoryFilterState,
  VcsDiffBrowser,
  VcsHistoryFilters,
  type VcsKindOption,
  VcsSettingsCard,
  VcsTimeline,
} from "@features/vcs-history";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag, toast } from "@shared/lib";
import { PageHead } from "./PageHead";
import { SectionCard } from "./SectionCard";

type Project = z.infer<typeof ProjectResponseSchema>;

export type VersionsViewProps = {
  project: Project;
};

type LastRestore = { result: VcsRestore; headBefore: string | null };

// Inclusive time window (ms) implied by the active date filter.
const dateWindow = (s: VcsHistoryFilterState): { from: number; to: number } => {
  const now = new Date();
  const startToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  switch (s.preset) {
    case "today":
      return { from: startToday, to: Infinity };
    case "7d":
      return { from: now.getTime() - 7 * 86_400_000, to: Infinity };
    case "30d":
      return { from: now.getTime() - 30 * 86_400_000, to: Infinity };
    case "custom":
      return {
        from: s.from ? new Date(`${s.from}T00:00:00`).getTime() : -Infinity,
        to: s.to ? new Date(`${s.to}T23:59:59.999`).getTime() : Infinity,
      };
    default:
      return { from: -Infinity, to: Infinity };
  }
};

const formatWhen = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleString(localeTag(), {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

export const VersionsView = ({ project }: VersionsViewProps) => {
  const { t } = useTranslation("workspace");
  const projectId = project.id;
  const { data: status, isLoading: statusLoading } = useVcsStatus(projectId);
  const { data: commits, isLoading: historyLoading } = useVcsHistory(projectId);
  const { mutate: initVcs, isPending: initing } = useInitVcs();
  const { mutate: createSnapshot, isPending: snapshotting } =
    useCreateVcsSnapshot();
  const { mutate: restore, isPending: restoring } = useRestoreVcs();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<VcsCommit | null>(null);
  const [message, setMessage] = useState("");
  const [lastRestore, setLastRestore] = useState<LastRestore | null>(null);
  const [filters, setFilters] =
    useState<VcsHistoryFilterState>(EMPTY_VCS_FILTERS);

  const { data: diff, isLoading: diffLoading } = useVcsDiff(
    projectId,
    selectedId ? { toId: selectedId } : {},
  );

  const handleSnapshot = () => {
    const msg = message.trim();
    if (!msg) return;
    createSnapshot(
      { projectId, message: msg },
      {
        onSuccess: (commit) => {
          setMessage("");
          toast.success(
            commit ? t("versions.versionSaved") : t("versions.noNewChanges"),
          );
        },
        onError: () => {
          toast.error(t("versions.saveVersionError"));
        },
      },
    );
  };

  const handleConfirmRestore = () => {
    if (!restoreTarget) return;
    const headBefore = status?.head ?? null;
    restore(
      { projectId, params: { commit_id: restoreTarget.id } },
      {
        onSuccess: (result) => {
          setLastRestore({ result, headBefore });
          setRestoreTarget(null);
          setSelectedId(null);
          toast.success(t("versions.restoreDone"));
        },
        onError: () => {
          toast.error(t("versions.restoreError"));
        },
      },
    );
  };

  const handleUndo = () => {
    if (!lastRestore) return;
    const target = lastRestore.result.pre_snapshot_id ?? lastRestore.headBefore;
    if (!target) return;
    restore(
      { projectId, params: { commit_id: target } },
      {
        onSuccess: () => {
          setLastRestore(null);
          toast.success(t("versions.undoneRestore"));
        },
        onError: () => {
          toast.error(t("versions.undoError"));
        },
      },
    );
  };

  const wrap = (children: React.ReactNode) => (
    <div
      style={{ padding: "24px 32px", overflowY: "auto", flex: 1, minHeight: 0 }}
    >
      <PageHead
        icon={History}
        title={t("versions.title")}
        sub={t("versions.subtitle")}
      />
      <div style={{ marginTop: 24 }}>{children}</div>
    </div>
  );

  if (statusLoading) {
    return wrap(
      <div className="flex justify-center" style={{ padding: 32 }}>
        <Spinner />
      </div>,
    );
  }

  if (status && !status.available) {
    return wrap(
      <SectionCard title={t("versions.unavailableTitle")}>
        <p
          className="dim"
          style={{ fontSize: 12.5, margin: 0, lineHeight: 1.6 }}
        >
          {t("versions.unavailableHint")}
        </p>
      </SectionCard>,
    );
  }

  if (status && !status.initialized) {
    return wrap(
      <SectionCard title={t("versions.notEnabledTitle")}>
        <p
          className="dim"
          style={{ fontSize: 12.5, margin: 0, lineHeight: 1.6 }}
        >
          {t("versions.notEnabledHint")}
        </p>
        <button
          type="button"
          className="btn primary"
          style={{ alignSelf: "flex-start" }}
          onClick={() => {
            initVcs(projectId);
          }}
          disabled={initing}
        >
          {initing ? <Spinner size="sm" /> : <History size={13} />}
          {t("versions.enableHistory")}
        </button>
      </SectionCard>,
    );
  }

  const all = commits ?? [];
  const named = all.filter((c) => c.kind === "manual");
  const auto = all.filter((c) => c.kind !== "manual");

  // Change-type chips, in a stable order, only for kinds that actually occur.
  const kindCounts = new Map<string, number>();
  auto.forEach((c) => {
    kindCounts.set(c.kind, (kindCounts.get(c.kind) ?? 0) + 1);
  });
  const kindLabels: Record<string, string> = {
    edit: t("versions.kindEdit"),
    compile: t("versions.kindCompile"),
    restore: t("versions.kindRestore"),
    init: t("versions.kindInit"),
  };
  const kindOptions: VcsKindOption[] = ["edit", "compile", "restore", "init"]
    .filter((k) => kindCounts.has(k))
    .map((k) => ({
      kind: k,
      label: kindLabels[k] ?? k,
      count: kindCounts.get(k) ?? 0,
    }));

  const win = dateWindow(filters);
  const query = filters.query.trim().toLowerCase();
  const filteredAuto = auto.filter((c) => {
    if (filters.kind !== "all" && c.kind !== filters.kind) return false;
    const t = new Date(c.created_at).getTime();
    if (t < win.from || t > win.to) return false;
    if (query && !c.message.toLowerCase().includes(query)) return false;
    return true;
  });

  return wrap(
    <div className="flex flex-col" style={{ gap: 20 }}>
      {/* status + save-version composer */}
      <SectionCard title={t("versions.saveVersionTitle")}>
        <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
          {t("versions.saveVersionHint", {
            when: formatWhen(status?.last_snapshot_at ?? null),
          })}
        </p>
        <div className="flex items-center" style={{ gap: 8 }}>
          <input
            className="input"
            style={{ flex: 1, fontSize: 12 }}
            placeholder={t("versions.versionNamePlaceholder")}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSnapshot();
            }}
          />
          <button
            type="button"
            className="btn primary"
            onClick={handleSnapshot}
            disabled={snapshotting || !message.trim()}
          >
            {snapshotting ? <Spinner size="sm" /> : <Camera size={13} />}
            {t("versions.saveVersion")}
          </button>
        </div>
      </SectionCard>

      {/* undo banner */}
      {lastRestore && (
        <div
          className="flex items-center"
          style={{
            gap: 10,
            padding: "10px 14px",
            borderRadius: "var(--r-2)",
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-line)",
          }}
        >
          <Undo2 size={14} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 12, flex: 1 }}>
            {t("versions.restoredBanner")}
          </span>
          <button
            type="button"
            className="btn xs"
            onClick={handleUndo}
            disabled={restoring}
          >
            {restoring ? <Spinner size="sm" /> : <Undo2 size={11} />}
            {t("versions.undo")}
          </button>
          <button
            type="button"
            className="btn xs ghost"
            onClick={() => {
              setLastRestore(null);
            }}
          >
            {t("versions.hide")}
          </button>
        </div>
      )}

      {/* versions: important | recent side by side */}
      {historyLoading ? (
        <div className="flex justify-center" style={{ padding: 24 }}>
          <Spinner size="sm" />
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.2fr)",
            gap: 20,
            alignItems: "start",
          }}
        >
          <div className="flex flex-col" style={{ gap: 8 }}>
            <h3 className="mono dim" style={SECTION_LABEL}>
              {t("versions.importantVersions")}
            </h3>
            {named.length === 0 ? (
              <div
                className="card dim flex items-center justify-center"
                style={{
                  gap: 8,
                  padding: 22,
                  fontSize: 12,
                  textAlign: "center",
                }}
              >
                <Bookmark size={14} />
                {t("versions.noNamedVersions")}
              </div>
            ) : (
              <VcsTimeline
                commits={named}
                variant="named"
                selectedId={selectedId}
                headId={status?.head ?? null}
                onSelect={setSelectedId}
                onRestore={setRestoreTarget}
              />
            )}
          </div>

          <div className="flex flex-col" style={{ gap: 10 }}>
            <h3 className="mono dim" style={SECTION_LABEL}>
              {t("versions.recentChanges")}
            </h3>
            {auto.length === 0 ? (
              <div
                className="card dim"
                style={{ padding: 22, fontSize: 12, textAlign: "center" }}
              >
                {t("versions.noChanges")}
              </div>
            ) : (
              <>
                <VcsHistoryFilters
                  state={filters}
                  onChange={setFilters}
                  kinds={kindOptions}
                  total={auto.length}
                  shown={filteredAuto.length}
                />
                {filteredAuto.length === 0 ? (
                  <div
                    className="card dim"
                    style={{
                      padding: 22,
                      fontSize: 12,
                      textAlign: "center",
                    }}
                  >
                    {t("versions.noMatch")}
                  </div>
                ) : (
                  <VcsTimeline
                    commits={filteredAuto}
                    variant="auto"
                    groupByDate
                    maxHeight={460}
                    selectedId={selectedId}
                    headId={status?.head ?? null}
                    onSelect={setSelectedId}
                    onRestore={setRestoreTarget}
                  />
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* what changed: full width */}
      <div className="flex flex-col" style={{ gap: 8 }}>
        <h3 className="mono dim" style={SECTION_LABEL}>
          {t("versions.whatChanged")}
        </h3>
        <VcsDiffBrowser
          diff={diff}
          isLoading={diffLoading && selectedId !== null}
        />
      </div>

      {/* settings */}
      <SectionCard title={t("versions.historySettings")}>
        <VcsSettingsCard projectId={projectId} />
      </SectionCard>

      <RestoreConfirmModal
        commit={restoreTarget}
        isPending={restoring}
        onClose={() => {
          setRestoreTarget(null);
        }}
        onConfirm={handleConfirmRestore}
      />
    </div>,
  );
};

const SECTION_LABEL: React.CSSProperties = {
  margin: 0,
  fontSize: 10.5,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};
