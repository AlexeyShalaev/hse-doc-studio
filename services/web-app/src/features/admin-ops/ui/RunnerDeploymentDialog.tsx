import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import { Badge, Button, Modal, TableSkeleton } from "@shared/ui";
import type {
  AdminRunnerDeployment,
  RunnerBuildIsolationView,
} from "@entities/session";
import { useRunnerDeployment } from "../api/opsQueries";
import { statusOf } from "../lib/viewStatus";
import { useNow } from "../lib/useNow";
import { useValue } from "../lib/isolationValue";
import {
  Block,
  FactList,
  PodFacts,
  ResourceFacts,
  SourceTag,
  type Fact,
} from "./IsolationParts";
import { Banner, ViewState } from "./parts";

/**
 * «Как развёрнут»: версия, откуда раннер, что он сообщил о себе и что видно
 * в кластере. Каждый блок подписан источником, чужие данные не смешиваются.
 */
export const RunnerDeploymentDialog = ({
  runner,
  onClose,
}: {
  runner: { id: string; name: string } | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const query = useRunnerDeployment(runner?.id ?? null);
  const status = statusOf(query);
  return (
    <Modal
      isOpen={runner !== null}
      onClose={onClose}
      width={640}
      title={t("dialog.title", { name: runner?.name ?? "" })}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("dialog.close")}
        </Button>
      }
    >
      <div data-testid="runner-deployment">
        {query.data ? (
          <RunnerDeploymentView info={query.data} />
        ) : (
          <ViewState
            status={status}
            errorText={t("dialog.loadFailed")}
            onRetry={() => void query.refetch()}
            compact
            skeleton={<TableSkeleton rows={6} columns={2} />}
            testId="runner-deployment"
          />
        )}
      </div>
    </Modal>
  );
};

const BuildFacts = ({
  build,
  kubernetes,
}: {
  build: RunnerBuildIsolationView;
  kubernetes: boolean;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  const network =
    build.network_disabled === null
      ? kubernetes
        ? t("dialog.networkPolicy")
        : t("value.none")
      : build.network_disabled
        ? t("dialog.networkOff")
        : t("dialog.networkOn");
  const items: Fact[] = [
    ...(kubernetes
      ? [{ label: t("dialog.namespace"), value: text(build.namespace) }]
      : []),
    { label: t("dialog.image"), value: text(build.image) },
    {
      label: t("dialog.network"),
      value: network,
      tone: build.network_disabled === false ? "warning" : undefined,
    },
    ...(kubernetes
      ? [
          { label: t("dialog.work"), value: text(build.work_size_limit) },
          { label: t("dialog.tmp"), value: text(build.tmp_size_limit) },
          {
            label: t("dialog.deadline"),
            value:
              build.active_deadline_s === null
                ? t("value.none")
                : t("value.seconds", { count: build.active_deadline_s }),
          },
          {
            label: t("dialog.runtimeClass"),
            value: build.runtime_class ?? t("value.default"),
          },
        ]
      : [
          { label: t("dialog.pids"), value: text(build.pids_limit) },
          { label: t("dialog.tmp"), value: text(build.tmp_size_limit) },
        ]),
  ];
  return (
    <>
      <FactList items={items} />
      <PodFacts resources={build.resources} security={build.security} />
    </>
  );
};

/** Содержимое карточки без окна: его рендерят тесты и галерея. */
export const RunnerDeploymentView = ({
  info,
}: {
  info: AdminRunnerDeployment;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text, flag } = useValue();
  const now = useNow();
  const { report, live } = info;
  const kubernetes = report?.executor === "kubernetes";
  const liveNote =
    info.live_status === "not_found" ||
    info.live_status === "forbidden" ||
    info.live_status === "unavailable"
      ? {
          not_found: t("dialog.liveStatus.not_found"),
          forbidden: t("dialog.liveStatus.forbidden"),
          unavailable: t("dialog.liveStatus.unavailable"),
        }[info.live_status]
      : null;

  return (
    <div className="iso-stack">
      {info.reinstall.length > 0 && (
        <Banner
          tone="warning"
          title={t("dialog.reinstallTitle")}
          testId="runner-deployment-reinstall"
        >
          {t("dialog.reinstallBody")}{" "}
          {info.reinstall
            .map((reason) =>
              reason === "before_limits"
                ? t("dialog.reason.before_limits")
                : t("dialog.reason.no_pod_limits"),
            )
            .join(" ")}
        </Banner>
      )}

      <FactList
        items={[
          {
            label: t("dialog.version"),
            testId: "runner-deployment-version",
            value: (
              <span
                style={{
                  display: "inline-flex",
                  flexWrap: "wrap",
                  gap: "0.375rem",
                }}
              >
                {t("dialog.versionValue", {
                  version: info.version,
                  studio: info.studio_version,
                })}
                {info.outdated && (
                  <Badge variant="warning">
                    <TriangleAlert size="0.6875rem" aria-hidden="true" />
                    {t("dialog.outdated")}
                  </Badge>
                )}
              </span>
            ),
          },
          {
            label: t("dialog.origin"),
            value:
              info.origin === null
                ? t("dialog.originValue.unknown")
                : {
                    chart: t("dialog.originValue.chart"),
                    ui: t("dialog.originValue.ui"),
                    other: t("dialog.originValue.other"),
                  }[info.origin],
          },
        ]}
      />

      <Block
        title={t("dialog.report")}
        testId="runner-deployment-report"
        source={
          <SourceTag
            kind="runner"
            extra={
              report?.reported_at
                ? t("dialog.reportedAt", {
                    ago: formatPastTime(report.reported_at, now),
                  })
                : null
            }
          />
        }
      >
        {report === null ? (
          <p className="iso-note" data-testid="runner-deployment-no-report">
            {t("dialog.noReport")}
          </p>
        ) : (
          <>
            <FactList
              items={[
                { label: t("dialog.executor"), value: report.executor },
                {
                  label: t("dialog.platform"),
                  value: {
                    kubernetes: t("dialog.platformValue.kubernetes"),
                    container: t("dialog.platformValue.container"),
                    host: t("dialog.platformValue.host"),
                  }[report.platform],
                },
                ...(report.platform === "kubernetes"
                  ? [
                      {
                        label: t("dialog.namespace"),
                        value: text(report.namespace),
                      },
                      { label: t("dialog.pod"), value: text(report.pod_name) },
                      {
                        label: t("dialog.serviceAccount"),
                        value: text(report.service_account),
                      },
                    ]
                  : []),
              ]}
            />
            <PodFacts resources={report.resources} security={report.security} />
          </>
        )}
      </Block>

      {report?.build && (
        <Block
          title={kubernetes ? t("dialog.build") : t("dialog.buildDocker")}
          source={<SourceTag kind="runner" />}
          testId="runner-deployment-build"
        >
          <BuildFacts build={report.build} kubernetes={kubernetes} />
        </Block>
      )}

      {live !== null && (
        <Block
          title={t("dialog.live")}
          source={<SourceTag kind="cluster" />}
          testId="runner-deployment-live"
        >
          <FactList
            items={[
              { label: t("dialog.namespace"), value: live.namespace },
              { label: t("dialog.image"), value: text(live.image) },
              {
                label: t("dialog.serviceAccount"),
                value: text(live.service_account),
              },
              { label: t("dialog.ready"), value: flag(live.ready) },
            ]}
          />
          <PodFacts resources={live.resources} security={live.security} />
          <p className="iso-sub">{t("dialog.liveBuild")}</p>
          {live.build_resources === null ? (
            <p className="iso-note">{t("dialog.liveBuildNone")}</p>
          ) : (
            <ResourceFacts resources={live.build_resources} />
          )}
        </Block>
      )}
      {liveNote && (
        <p className="iso-note" data-testid="runner-deployment-live-note">
          {liveNote}
        </p>
      )}
    </div>
  );
};
