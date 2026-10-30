import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { Button, PageHeader } from "@shared/ui";
import { useQueueSummary, useRunnerSummary } from "../api/opsQueries";
import { LONG_WAIT_S } from "../lib/jobs";
import { liveRunners } from "../lib/runnerStatus";
import { Queue } from "./Queue";
import { Runners } from "./Runners";
import { Tabs } from "./parts";

type Tab = "runners" | "queue";

/**
 * Раздел «Раннеры и очередь»: один заголовок, под ним вкладки, под вкладками вид.
 * Вкладка живёт в адресе (tab=queue) вместе с поиском и фильтрами списков,
 * поэтому ссылка открывает тот же вид.
 */
export const RunnersPage = ({
  initialTab = "runners",
  initialCreateToken = false,
}: {
  initialTab?: Tab;
  initialCreateToken?: boolean;
}) => {
  const { t } = useTranslation("adminOps");
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("tab");
  const tab: Tab =
    fromUrl === "queue" || fromUrl === "runners" ? fromUrl : initialTab;
  const [creating, setCreating] = useState(initialCreateToken);
  const runners = useRunnerSummary();
  const summary = useQueueSummary();

  const counts = runners.data;
  const live = counts ? liveRunners(counts) : 0;
  const noneOnline = counts !== undefined && live > 0 && counts.online === 0;
  const waiting = summary.data;
  const stuck =
    waiting?.oldest_queued_age_s != null &&
    waiting.oldest_queued_age_s >= LONG_WAIT_S;

  // Смена вкладки начинает её вид с чистого адреса: фильтры одной вкладки
  // другой не нужны.
  const setTab = (next: Tab) => {
    if (next === tab) return;
    setParams(new URLSearchParams({ tab: next }));
  };

  return (
    <div className="ops-stack" data-testid="runners-page">
      <PageHeader
        title={t("page.title")}
        description={t("page.lead")}
        actions={
          tab === "runners" ? (
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => {
                setCreating(true);
              }}
              style={{ gap: 6 }}
              data-testid="runner-token-create"
            >
              <Plus size={14} aria-hidden="true" />
              {t("tokens.create")}
            </Button>
          ) : undefined
        }
        tabs={
          <Tabs
            label={t("tabs.label")}
            value={tab}
            onChange={setTab}
            tabs={[
              {
                id: "runners",
                label: t("tabs.runners"),
                ...(counts
                  ? {
                      count: live,
                      countTone: noneOnline ? "danger" : "neutral",
                    }
                  : {}),
              },
              {
                id: "queue",
                label: t("tabs.queue"),
                ...(waiting
                  ? {
                      count: waiting.queued + waiting.running,
                      countTone: stuck ? "warning" : "neutral",
                    }
                  : {}),
              },
            ]}
          />
        }
      />
      <div
        id="ops-tab-panel"
        role="tabpanel"
        aria-labelledby={`ops-tab-${tab}`}
        className="ops-stack"
      >
        {tab === "runners" ? (
          <Runners
            creating={creating}
            onCreatingChange={setCreating}
            onOpenQueue={() => {
              setTab("queue");
            }}
          />
        ) : (
          <Queue />
        )}
      </div>
    </div>
  );
};
