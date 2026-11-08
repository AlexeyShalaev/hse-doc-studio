import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import type { DocBuildView } from "@entities/project-build";
import { useDocBuilds } from "../model/useDocBuilds";
import { useFetchBuild } from "../model/useFetchBuild";
import { useDocBuildText } from "./DocBuildLine";

export type DocBuildNoteViewProps = {
  view: DocBuildView;
  now: number;
  pending: boolean;
  onFetch: (force: boolean) => void;
};

/** Полоса сборки документа: где и когда собран, из какого коммита, свежий ли, и кнопка «Получить сборку». */
export const DocBuildNoteView = ({
  view,
  now,
  pending,
  onFetch,
}: DocBuildNoteViewProps) => {
  const { t } = useTranslation("devices");
  const text = useDocBuildText(view, now);
  return (
    <div
      className="flex items-center"
      style={{
        gap: "0.625rem",
        padding: "0.375rem 1rem",
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-1)",
        fontSize: "0.75rem",
        flexWrap: "wrap",
      }}
      data-testid="doc-build-note"
      data-build={view.key}
    >
      <span>{text.main}</span>
      {text.freshness !== null && (
        <span
          className="chip sans"
          style={{
            fontSize: "0.65625rem",
            color: view.fresh === false ? "var(--c-warn)" : "var(--c-ok)",
          }}
        >
          {text.freshness}
        </span>
      )}
      {text.commit !== null && (
        <span className="mono dim" style={{ fontSize: "0.6875rem" }}>
          {text.commit}
        </span>
      )}
      {view.fromCloud && (
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {t("builds.local.from")}
        </span>
      )}
      {view.fetchBlocked !== null && (
        <span
          className="dim"
          style={{ fontSize: "0.6875rem" }}
          data-testid="doc-build-blocked"
        >
          {t(`builds.blocked.${view.fetchBlocked}`)}
        </span>
      )}
      {view.canFetch && (
        <Button
          size="xs"
          variant="primary"
          disabled={pending}
          onClick={() => {
            onFetch(false);
          }}
          data-testid="doc-build-fetch"
        >
          <Download size="0.6875rem" />
          {pending ? t("builds.fetching") : t("builds.fetch")}
        </Button>
      )}
      {view.localNewer && (
        <Button
          size="xs"
          variant="ghost"
          disabled={pending}
          onClick={() => {
            onFetch(true);
          }}
          data-testid="doc-build-force"
        >
          {t("builds.forceFetch")}
        </Button>
      )}
    </div>
  );
};

/** В панели сборки документа (облако и локальная Студия): данные из `useDocBuilds`. */
export const DocBuildNote = ({
  projectId,
  docId,
}: {
  projectId: string;
  docId: string;
}) => {
  const builds = useDocBuilds(projectId);
  const fetchBuild = useFetchBuild(projectId);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, 30_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  const view = builds.byDoc.get(docId);
  if (view === undefined) return null;
  return (
    <DocBuildNoteView
      view={view}
      now={now}
      pending={fetchBuild.isPending}
      onFetch={(force) => {
        fetchBuild.run(docId, force);
      }}
    />
  );
};
