import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, PageHeader } from "@shared/ui";
import { useQueueSummary, useRunners } from "../api/opsQueries";
import { LONG_WAIT_S } from "../lib/jobs";
import { countOnline } from "../lib/runnerStatus";
import { useNow } from "../lib/useNow";
import { Queue } from "./Queue";
import { Runners } from "./Runners";
import { Tabs } from "./parts";

type Tab = "runners" | "queue";

/** Раздел «Раннеры и очередь»: один заголовок, под ним вкладки, под вкладками вид. */
export const RunnersPage = ({
  initialTab = "runners",
  initialCreateToken = false,
}: {
  initialTab?: Tab;
  initialCreateToken?: boolean;
}) => {
  const { t } = useTranslation("adminOps");
  const [tab, setTab] = useState<Tab>(initialTab);
  const [creating, setCreating] = useState(initialCreateToken);
  const runners = useRunners();
  const summary = useQueueSummary();
  const now = useNow();

  const live = (runners.data ?? []).filter((r) => !r.revoked);
  const noneOnline = live.length > 0 && countOnline(live, now) === 0;
  const waiting = summary.data;
  const stuck =
    waiting?.oldest_queued_age_s != null &&
    waiting.oldest_queued_age_s >= LONG_WAIT_S;

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
                ...(runners.data
                  ? {
                      count: live.length,
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
