import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { useDocBuilds } from "../model/useDocBuilds";
import { shortCommit, type DocBuildView } from "@entities/project-build";

const COLOR = {
  ok: "var(--c-ok)",
  info: "var(--c-info)",
  warn: "var(--c-warn)",
  muted: "var(--fg-3)",
} as const;

/** Текст строки о сборке документа: где, когда, из какого коммита и свежая ли. */
export const useDocBuildText = (view: DocBuildView, now: number) => {
  const { t } = useTranslation("devices");
  const when = view.at === null ? "" : formatPastTime(view.at, now);
  const when2 = view.at2 === null ? "" : formatPastTime(view.at2, now);
  const main =
    view.key === "both"
      ? t("builds.both", { cloud: when, studio: when2 })
      : t(`builds.${view.key}`, { when });
  const commit = shortCommit(view.commit);
  const freshness =
    view.key === "none" || view.running
      ? null
      : view.fresh === true
        ? t("builds.fresh")
        : view.fresh === false
          ? t("builds.stale")
          : null;
  return {
    main,
    freshness,
    commit: commit === null ? null : t("builds.commit", { commit }),
  };
};

/** Короткий возраст для тесного списка: «5 мин», «2 ч», «3 дн». */
export const shortAgo = (t: TFunction, iso: string, now: number): string => {
  const minutes = Math.max(
    0,
    Math.round((now - new Date(iso).getTime()) / 60_000),
  );
  if (minutes < 1) return t("time.now");
  if (minutes < 60) return t("time.min", { count: minutes });
  if (minutes < 60 * 24)
    return t("time.hour", { count: Math.round(minutes / 60) });
  return t("time.day", { count: Math.round(minutes / 1440) });
};

export type DocBuildLineProps = {
  view: DocBuildView;
  now: number;
  docId: string;
};

/** Одна строка под названием документа: видно без захода в документ. */
export const DocBuildLine = ({ view, now, docId }: DocBuildLineProps) => {
  const { t } = useTranslation("devices");
  const text = useDocBuildText(view, now);
  const when = view.at === null ? "" : shortAgo(t, view.at, now);
  const when2 = view.at2 === null ? "" : shortAgo(t, view.at2, now);
  const compact =
    view.key === "both"
      ? t("builds.short.both", { cloud: when, studio: when2 })
      : t(`builds.short.${view.key}`, { when });
  return (
    <span
      className="flex items-baseline"
      style={{
        columnGap: "0.375rem",
        rowGap: "0.0625rem",
        flexWrap: "wrap",
        overflowWrap: "anywhere",
        fontSize: "0.65625rem",
        lineHeight: 1.3,
        color: COLOR[view.tone],
        minWidth: 0,
      }}
      data-testid={`doc-build-${docId}`}
      data-build={view.key}
      data-fresh={view.fresh === null ? undefined : String(view.fresh)}
      title={[text.main, text.freshness, text.commit]
        .filter(Boolean)
        .join(", ")}
    >
      <span style={{ minWidth: 0 }}>{compact}</span>
      {text.freshness !== null && (
        <span
          style={{
            minWidth: 0,
            color: view.fresh === false ? "var(--c-warn)" : "var(--fg-3)",
          }}
        >
          {text.freshness}
        </span>
      )}
    </span>
  );
};

/** Строка под названием документа в списке: сама берёт данные, ничего не показывает, пока их нет. */
export const DocBuildSubline = ({
  projectId,
  docId,
  now,
}: {
  projectId: string;
  docId: string;
  now: number;
}) => {
  const builds = useDocBuilds(projectId);
  const view = builds.byDoc.get(docId);
  if (view === undefined) return null;
  return <DocBuildLine view={view} now={now} docId={docId} />;
};
