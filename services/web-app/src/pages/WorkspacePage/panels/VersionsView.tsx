import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bookmark, Camera, History, Undo2 } from "lucide-react";
import type { z } from "zod";
import { useSyncStatus, useSyncUiStore } from "@entities/git-sync";
import type { ProjectResponseSchema } from "@entities/project";
import { useProfile } from "@entities/profile";
import {
  type VcsCommit,
  type VcsHistoryParams,
  type VcsRestore,
  useCreateVcsSnapshot,
  useInfiniteVcsHistory,
  useInitVcs,
  useRestoreVcs,
  useVcsDiff,
  useVcsHistoryFacets,
  useVcsHistoryPage,
  useVcsStatus,
} from "@entities/vcs";
import { SyncPanel, type SyncHistoryMode } from "@features/git-sync";
import {
  AUTHOR_ALL,
  AUTHOR_MINE,
  EMPTY_VCS_FILTERS,
  NAMED_KIND,
  RestoreConfirmModal,
  type VcsAuthorOption,
  type VcsHistoryFilterState,
  VcsDiffBrowser,
  VcsHistoryFilters,
  type VcsKindOption,
  VcsSettingsCard,
  VcsTimeline,
  buildHistoryParams,
  isVcsFiltersActive,
  kindChipIds,
  recentTotal,
} from "@features/vcs-history";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag, toast, useDebouncedValue } from "@shared/lib";
import { PageHead } from "./PageHead";
import { SectionCard } from "./SectionCard";

type Project = z.infer<typeof ProjectResponseSchema>;

export type VersionsViewProps = {
  project: Project;
};

type LastRestore = { result: VcsRestore; headBefore: string | null };

// Именные версии: их немного, поэтому одной страницы хватает.
const NAMED_PARAMS: VcsHistoryParams = { kind: [NAMED_KIND], limit: 100 };

const SEARCH_DEBOUNCE_MS = 300;

const formatWhen = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleString(localeTag(), {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

// Что изменилось в версии, пришедшей из репозитория: объекты уже в хранилище
// после проверки, так что обычный запрос различий её видит.
const IncomingCommitDiff = ({
  projectId,
  commitId,
}: {
  projectId: string;
  commitId: string;
}) => {
  const { t } = useTranslation("workspace");
  const { data: diff, isLoading } = useVcsDiff(projectId, { toId: commitId });
  return (
    <div className="flex flex-col" style={{ gap: 8 }}>
      <h3 className="mono dim" style={SECTION_LABEL}>
        {t("versions.incomingChanges")}
      </h3>
      <VcsDiffBrowser diff={diff} isLoading={isLoading} />
    </div>
  );
};

export const VersionsView = ({ project }: VersionsViewProps) => {
  const { t } = useTranslation("workspace");
  const projectId = project.id;
  const { data: status, isLoading: statusLoading } = useVcsStatus(projectId);
  const { data: facets } = useVcsHistoryFacets(projectId);
  const { data: profile } = useProfile();
  const { data: gitStatus } = useSyncStatus(projectId);
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
  const recentRef = useRef<HTMLDivElement>(null);

  const syncSupported = gitStatus?.supported === true;
  const connected = syncSupported && gitStatus.connected;
  // «Мои» считаем по e-mail из профиля; пока профиль не заполнен, такого фильтра нет.
  const mineEmail =
    profile && !profile.is_default ? profile.effective_email : null;

  // Поле поиска обновляется сразу, а запрос уходит после паузы в наборе.
  const debouncedQuery = useDebouncedValue(filters.query, SEARCH_DEBOUNCE_MS);
  const effectiveFilters = useMemo<VcsHistoryFilterState>(
    () => ({
      ...filters,
      query: debouncedQuery,
      // Репозиторий отключили, пока был выбран «Не отправлены»: условие снимаем.
      sync: connected ? filters.sync : "all",
    }),
    [connected, debouncedQuery, filters],
  );
  const params = useMemo(
    () =>
      buildHistoryParams(effectiveFilters, {
        mineEmail,
        facetKinds: facets?.kinds,
      }),
    [effectiveFilters, facets?.kinds, mineEmail],
  );

  const { data: namedPage, isLoading: namedLoading } = useVcsHistoryPage(
    projectId,
    NAMED_PARAMS,
  );
  const {
    data: recentPages,
    isLoading: recentLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useInfiniteVcsHistory(projectId, params);

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

  const handleShowInHistory = (mode: SyncHistoryMode) => {
    setFilters({ ...EMPTY_VCS_FILTERS, sync: mode });
    recentRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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

  const named = (namedPage ?? []).filter((c) => c.kind === NAMED_KIND);
  // Именные версии показаны слева, поэтому из ленты их убираем.
  const recent = (recentPages?.pages.flat() ?? []).filter(
    (c) => c.kind !== NAMED_KIND,
  );
  const filtersActive = isVcsFiltersActive(filters);
  const total = facets ? recentTotal(facets.kinds) : recent.length;
  const historyLoading = namedLoading || recentLoading;

  const kindLabels: Record<string, string> = {
    edit: t("versions.kindEdit"),
    compile: t("versions.kindCompile"),
    restore: t("versions.kindRestore"),
    init: t("versions.kindInit"),
    template_update: t("versions.kindTemplateUpdate"),
    sync: t("versions.kindSync"),
    other: t("versions.kindOther"),
  };
  const kindOptions: VcsKindOption[] = kindChipIds(
    facets?.kinds ?? {},
    filters.kinds,
  ).map(({ kind, count }) => ({
    kind,
    label: kindLabels[kind] ?? kind,
    count,
  }));

  const authorOptions: VcsAuthorOption[] = [
    { value: AUTHOR_ALL, label: t("versions.authorAll") },
  ];
  if (mineEmail) {
    authorOptions.push({ value: AUTHOR_MINE, label: t("versions.authorMine") });
  }
  const seenEmails = new Set<string>(
    mineEmail ? [mineEmail.toLowerCase()] : [],
  );
  for (const author of facets?.authors ?? []) {
    const email = author.email?.trim();
    if (!email || seenEmails.has(email.toLowerCase())) continue;
    seenEmails.add(email.toLowerCase());
    authorOptions.push({ value: email, label: author.name });
  }

  return wrap(
    <div className="flex flex-col" style={{ gap: 20 }}>
      {/* sync with a repository */}
      {syncSupported && (
        <SectionCard title={t("versions.syncTitle")}>
          <SyncPanel
            projectId={projectId}
            onConnect={() => {
              useSyncUiStore.getState().openConnectDialog("connect");
            }}
            onBundle={() => {
              useSyncUiStore.getState().openBundleDialog();
            }}
            onShowInHistory={handleShowInHistory}
            renderIncomingDetails={(commitId) => (
              <IncomingCommitDiff projectId={projectId} commitId={commitId} />
            )}
          />
        </SectionCard>
      )}

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
                meEmail={mineEmail}
                onSelect={setSelectedId}
                onRestore={setRestoreTarget}
              />
            )}
          </div>

          <div
            ref={recentRef}
            className="flex flex-col"
            style={{ gap: 10, scrollMarginTop: 8 }}
          >
            <h3 className="mono dim" style={SECTION_LABEL}>
              {t("versions.recentChanges")}
            </h3>
            {total === 0 && recent.length === 0 && !filtersActive ? (
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
                  authors={authorOptions}
                  showSync={connected}
                  total={total}
                  shown={recent.length}
                  hasMore={hasNextPage}
                />
                {recent.length === 0 ? (
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
                    commits={recent}
                    variant="auto"
                    groupByDate
                    maxHeight={460}
                    selectedId={selectedId}
                    headId={status?.head ?? null}
                    meEmail={mineEmail}
                    hasMore={hasNextPage}
                    isLoadingMore={isFetchingNextPage}
                    onLoadMore={() => {
                      void fetchNextPage();
                    }}
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
