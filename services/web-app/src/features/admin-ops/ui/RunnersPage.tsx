import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueueSummary, useRunners } from "../api/opsQueries";
import { Queue } from "./Queue";
import { Runners } from "./Runners";
import { HeaderTabsContext } from "../lib/headerTabs";
import { Tabs } from "./parts";

type Tab = "runners" | "queue";

/** Раздел «Раннеры и очередь»: две вкладки прямо под заголовком вида. */
export const RunnersPage = ({
  initialTab = "runners",
  initialCreateToken = false,
}: {
  initialTab?: Tab;
  initialCreateToken?: boolean;
}) => {
  const { t } = useTranslation("adminOps");
  const [tab, setTab] = useState<Tab>(initialTab);
  const runners = useRunners();
  const summary = useQueueSummary();
  const tabs = (
    <Tabs
      label={t("tabs.label")}
      value={tab}
      onChange={setTab}
      tabs={[
        {
          id: "runners",
          label: t("tabs.runners"),
          ...(runners.data
            ? { count: runners.data.filter((r) => !r.revoked).length }
            : {}),
        },
        {
          id: "queue",
          label: t("tabs.queue"),
          ...(summary.data
            ? { count: summary.data.queued + summary.data.running }
            : {}),
        },
      ]}
    />
  );
  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="runners-page"
    >
      <HeaderTabsContext.Provider value={tabs}>
        {tab === "runners" ? (
          <Runners initialCreateToken={initialCreateToken} />
        ) : (
          <Queue />
        )}
      </HeaderTabsContext.Provider>
    </div>
  );
};
