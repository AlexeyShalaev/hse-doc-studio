import { useTranslation } from "react-i18next";
import { formatPastTime } from "@shared/lib";
import type { AdminRunnerIsolation } from "@entities/session";
import { useValue } from "../lib/isolationValue";
import {
  Block,
  FactList,
  PodFacts,
  ResourceFacts,
  SourceTag,
  type SourceKind,
} from "./IsolationParts";
import { Banner } from "./parts";

type Isolation = AdminRunnerIsolation;
type Check = { declared: boolean | null; live: boolean | null };

/** Метка проверки: проверено в кластере, не найдено, или только задано. */
const checkKind = (check: Check, liveRead: boolean): SourceKind =>
  check.live === true
    ? "checked"
    : check.live === false
      ? "missing"
      : liveRead
        ? "unchecked"
        : "declared";

/** Строка политики: задано ли и что показал кластер. */
const PolicyLine = ({
  label,
  check,
  liveRead,
  testId,
}: {
  label: string;
  check: Check;
  liveRead: boolean;
  testId: string;
}) => {
  const { flag } = useValue();
  return (
    <FactList
      items={[
        {
          label,
          testId,
          tone: check.declared === false ? "warning" : undefined,
          value: (
            <span
              style={{
                display: "inline-flex",
                flexWrap: "wrap",
                gap: "0.375rem",
                alignItems: "center",
              }}
            >
              {flag(check.declared)}
              {(check.declared === true || check.live !== null) && (
                <SourceTag kind={checkKind(check, liveRead)} />
              )}
            </span>
          ),
        },
      ]}
    />
  );
};

const LiveLine = ({ info, now }: { info: Isolation; now: number }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const ago = info.checked_at ? formatPastTime(info.checked_at, now) : "";
  const text = {
    off: t("panel.live.off"),
    ok: t("panel.live.ok", { ago }),
    partial: t("panel.live.partial", { ago }),
    forbidden: t("panel.live.forbidden"),
    unavailable: t("panel.live.unavailable"),
  }[info.live_read];
  return (
    <p
      className="iso-note"
      data-testid="isolation-live"
      data-live={info.live_read}
    >
      {text}
    </p>
  );
};

const ChartRunner = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  const chart = info.chart_runner;
  if (chart === null) return null;
  return (
    <Block
      title={t("panel.chart.title")}
      source={<SourceTag kind="config" />}
      testId="isolation-chart"
    >
      {!chart.enabled ? (
        <p className="iso-note">{t("panel.chart.disabled")}</p>
      ) : (
        <>
          {chart.docker_socket && (
            <Banner
              tone="warning"
              title={t("panel.chart.dockerSocket")}
              testId="isolation-docker-socket"
            />
          )}
          <FactList
            items={[
              { label: t("dialog.executor"), value: chart.executor },
              { label: t("panel.chart.replicas"), value: chart.replicas },
              { label: t("dialog.namespace"), value: text(chart.namespace) },
              {
                label: t("dialog.serviceAccount"),
                value: text(chart.service_account),
              },
              {
                label: t("panel.chart.storage"),
                value: [
                  chart.storage.kind === null
                    ? t("value.none")
                    : {
                        pvc: t("panel.chart.storageKind.pvc"),
                        host_path: t("panel.chart.storageKind.host_path"),
                        empty_dir: t("panel.chart.storageKind.empty_dir"),
                      }[chart.storage.kind],
                  chart.storage.storage_class,
                  chart.storage.size,
                ]
                  .filter(Boolean)
                  .join(", "),
              },
              {
                label: t("panel.chart.tmp"),
                value: text(chart.tmp_size_limit),
              },
              {
                label: t("panel.chart.office"),
                value: chart.office_url ?? t("panel.office.none"),
                testId: "isolation-chart-office",
              },
            ]}
          />
          <PodFacts resources={chart.resources} security={chart.security} />
        </>
      )}
    </Block>
  );
};

const BuildPods = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  const build = info.build;
  if (info.config === "none") return null;
  return (
    <Block
      title={t("panel.build.title")}
      source={<SourceTag kind="config" />}
      testId="isolation-build"
    >
      {build === null ? (
        <p className="iso-note">{t("panel.build.none")}</p>
      ) : (
        <>
          <FactList
            items={[
              { label: t("dialog.namespace"), value: text(build.namespace) },
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
            ]}
          />
          <PodFacts resources={build.resources} security={build.security} />
        </>
      )}
    </Block>
  );
};

const InstallFromUi = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  const ui = info.install_from_ui;
  const b = ui.bounds;
  return (
    <Block
      title={t("panel.install.title")}
      source={<SourceTag kind="config" />}
      testId="isolation-install"
    >
      {!ui.enabled ? (
        <p className="iso-note">{t("panel.install.disabled")}</p>
      ) : (
        <FactList
          items={[
            { label: t("dialog.namespace"), value: text(ui.namespace) },
            {
              label: t("panel.install.buildNamespace"),
              value: text(ui.build_namespace),
              testId: "isolation-install-build-ns",
            },
            {
              label: t("dialog.serviceAccount"),
              value: text(ui.service_account),
            },
            {
              label: t("panel.install.storage"),
              value: [
                ui.storage_class ?? t("value.default"),
                ui.storage_size,
              ].join(", "),
            },
            {
              label: t("panel.install.office"),
              value: ui.office_url ?? t("panel.office.none"),
              testId: "isolation-install-office",
            },
          ]}
        />
      )}
      <p className="iso-sub">{t("panel.install.runner")}</p>
      <ResourceFacts resources={ui.runner} />
      <p className="iso-sub">{t("panel.install.build")}</p>
      <ResourceFacts resources={ui.build} />
      <p className="iso-sub">{t("panel.install.bounds")}</p>
      <ul className="iso-list" data-testid="isolation-bounds">
        <li>
          {t("panel.install.cpuBounds", {
            runner: b.min_runner_cpu,
            build: b.min_build_cpu,
            max: b.max_cpu,
          })}
        </li>
        <li>
          {t("panel.install.memoryBounds", {
            runner: b.min_runner_memory,
            build: b.min_build_memory,
            max: b.max_memory,
          })}
        </li>
      </ul>
    </Block>
  );
};

const Network = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const net = info.network;
  if (net === null) return null;
  const liveRead = info.live_read !== "off";
  const egress = net.runner_egress;
  return (
    <Block title={t("panel.network.title")} testId="isolation-network">
      <PolicyLine
        label={t("panel.network.buildDenyAll")}
        check={net.build_deny_all}
        liveRead={liveRead}
        testId="isolation-build-deny"
      />
      <PolicyLine
        label={t("panel.network.uiBuildDenyAll")}
        check={net.ui_build_deny_all}
        liveRead={liveRead}
        testId="isolation-ui-build-deny"
      />
      <PolicyLine
        label={t("panel.network.runnerEgress")}
        check={egress}
        liveRead={liveRead}
        testId="isolation-egress"
      />
      {egress.declared && (
        <>
          <p className="iso-sub">{t("panel.network.allows")}</p>
          <ul className="iso-list" data-testid="isolation-egress-allows">
            {egress.dns && <li>{t("panel.network.dns")}</li>}
            {egress.studio_port !== null && (
              <li>{t("panel.network.studio", { port: egress.studio_port })}</li>
            )}
            <li>
              {t("panel.network.apiServer", {
                cidrs:
                  egress.api_server_cidrs.length > 0
                    ? egress.api_server_cidrs.join(", ")
                    : t("panel.network.anyAddress"),
                ports: egress.api_server_ports.join(", "),
              })}
            </li>
            {egress.office_port !== null && (
              <li>{t("panel.network.office", { port: egress.office_port })}</li>
            )}
            {egress.extra_rules > 0 && (
              <li>{t("panel.network.extra", { count: egress.extra_rules })}</li>
            )}
          </ul>
        </>
      )}
      <p className="iso-note">{t("panel.network.cni")}</p>
    </Block>
  );
};

/** Встроенный Gotenberg: куда раннеры ходят с офисными задачами. */
const OfficeConvert = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { flag, text } = useValue();
  const office = info.office_convert;
  if (office === null) return null;
  return (
    <Block
      title={t("panel.office.title")}
      source={<SourceTag kind="config" />}
      testId="isolation-office"
    >
      <p className="iso-note">{t("panel.office.lead")}</p>
      <FactList
        items={[
          {
            label: t("panel.office.url"),
            value: office.url,
            testId: "isolation-office-url",
          },
          { label: t("panel.office.image"), value: text(office.image) },
          { label: t("panel.office.replicas"), value: office.replicas },
          {
            label: t("panel.office.networkPolicy"),
            value: flag(office.network_policy),
            tone: office.network_policy ? undefined : "warning",
          },
        ]}
      />
      <ResourceFacts resources={office.resources} />
    </Block>
  );
};

type QuotaInfo = NonNullable<Isolation["quota"]>;
type LimitRangeInfo = NonNullable<Isolation["limit_range"]>;

const Quota = ({
  quota,
  title,
  testId,
}: {
  quota: QuotaInfo | null;
  title: string;
  testId: string;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  if (quota === null) return null;
  const keys = [
    ...new Set([
      ...Object.keys(quota.declared ?? {}),
      ...Object.keys(quota.live_hard ?? {}),
    ]),
  ];
  const source: SourceKind =
    quota.live_found === true
      ? "checked"
      : quota.live_found === false
        ? "missing"
        : "config";
  return (
    <Block
      title={`${title}${quota.namespace ? ` (${quota.namespace})` : ""}`}
      source={
        quota.declared !== null || quota.live_found !== null ? (
          <SourceTag kind={source} />
        ) : null
      }
      testId={testId}
    >
      {keys.length === 0 ? (
        <p className="iso-note">{t("panel.quota.off")}</p>
      ) : (
        <table className="iso-table">
          <thead>
            <tr>
              <th scope="col">{t("panel.quota.key")}</th>
              <th scope="col">{t("panel.quota.declared")}</th>
              {quota.live_hard !== null && (
                <>
                  <th scope="col">{t("panel.quota.hard")}</th>
                  <th scope="col">{t("panel.quota.used")}</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{text(quota.declared?.[key])}</td>
                {quota.live_hard !== null && (
                  <>
                    <td>{text(quota.live_hard[key])}</td>
                    <td>{text(quota.live_used?.[key])}</td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Block>
  );
};

const LimitRange = ({
  range,
  title,
  testId,
}: {
  range: LimitRangeInfo | null;
  title: string;
  testId: string;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  if (range === null) return null;
  const join = (values: Record<string, string> | undefined) =>
    values && Object.keys(values).length > 0
      ? Object.entries(values)
          .map(([k, v]) => `${k} ${v}`)
          .join(", ")
      : t("value.none");
  const rows = (values: {
    default: Record<string, string>;
    default_request: Record<string, string>;
    max: Record<string, string>;
  }) => [
    { label: t("panel.limitRange.default"), value: join(values.default) },
    {
      label: t("panel.limitRange.defaultRequest"),
      value: join(values.default_request),
    },
    { label: t("panel.limitRange.max"), value: join(values.max) },
  ];
  return (
    <Block
      title={`${title}${range.namespace ? ` (${range.namespace})` : ""}`}
      testId={testId}
    >
      {range.declared === null && range.live === null ? (
        <p className="iso-note">{t("panel.limitRange.off")}</p>
      ) : null}
      {range.declared !== null && (
        <>
          <p className="iso-sub">
            <SourceTag kind="config" />
          </p>
          <FactList items={rows(range.declared)} />
        </>
      )}
      {range.live_found !== null &&
        (range.live !== null || range.declared !== null) && (
          <>
            <p className="iso-sub">
              <SourceTag kind={range.live !== null ? "checked" : "missing"} />
            </p>
            {range.live !== null && <FactList items={rows(range.live)} />}
          </>
        )}
    </Block>
  );
};

const PodSecurity = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const list = info.pod_security;
  return (
    <Block
      title={t("panel.podSecurity.title")}
      source={<SourceTag kind={list === null ? "unchecked" : "checked"} />}
      testId="isolation-pod-security"
    >
      {list === null ? (
        <p className="iso-note">{t("panel.podSecurity.unchecked")}</p>
      ) : (
        list.map((ns) => (
          <div key={ns.namespace} className="iso-block">
            <p className="iso-sub">{ns.namespace}</p>
            <FactList
              items={[
                {
                  label: t("panel.podSecurity.enforce"),
                  value: ns.enforce
                    ? [ns.enforce, ns.enforce_version]
                        .filter(Boolean)
                        .join(", ")
                    : t("panel.podSecurity.noLabel"),
                  tone: ns.enforce === "restricted" ? undefined : "warning",
                },
                {
                  label: t("panel.podSecurity.warn"),
                  value: ns.warn ?? t("panel.podSecurity.noLabel"),
                },
                {
                  label: t("panel.podSecurity.audit"),
                  value: ns.audit ?? t("panel.podSecurity.noLabel"),
                },
              ]}
            />
            {ns.enforce !== "restricted" && (
              <p className="iso-note">{t("panel.podSecurity.notRestricted")}</p>
            )}
          </div>
        ))
      )}
    </Block>
  );
};

/** Сводка: откуда данные и проверено ли в кластере. */
export const IsolationSummary = ({
  info,
  now,
}: {
  info: Isolation;
  now: number;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  return (
    <div className="iso-block" data-testid="isolation-summary">
      <p className="iso-block-head">
        {info.config === "helm" ? (
          <>
            <span>{t("panel.sourceHelm")}</span>
            {info.release_namespace && (
              <span className="ops-muted" style={{ fontWeight: 400 }}>
                {t("panel.releaseNamespace")}: {info.release_namespace}
              </span>
            )}
          </>
        ) : (
          <span style={{ fontWeight: 400 }} data-testid="isolation-no-helm">
            {t("panel.sourceNone")}
          </span>
        )}
      </p>
      {info.config === "helm" && <LiveLine info={info} now={now} />}
    </div>
  );
};

/** Подробности: раннер чарта, поды сборки, установка из админки, сеть, квота, Pod Security. */
export const ClusterIsolationView = ({ info }: { info: Isolation }) => {
  const { t } = useTranslation("adminRunnerIsolation");
  return (
    <div className="iso-stack" data-testid="isolation-details">
      <div className="iso-grid">
        <ChartRunner info={info} />
        <BuildPods info={info} />
        <InstallFromUi info={info} />
      </div>
      {info.config === "helm" && (
        <div className="iso-grid">
          <Network info={info} />
          <OfficeConvert info={info} />
          <Quota
            quota={info.quota}
            title={t("panel.quota.title")}
            testId="isolation-quota"
          />
          <LimitRange
            range={info.limit_range}
            title={t("panel.limitRange.title")}
            testId="isolation-limit-range"
          />
          {/* Свой namespace подов сборки раннеров из админки: квота и LimitRange там отдельные. */}
          <Quota
            quota={info.ui_quota}
            title={t("panel.quota.titleUi")}
            testId="isolation-ui-quota"
          />
          <LimitRange
            range={info.ui_limit_range}
            title={t("panel.limitRange.titleUi")}
            testId="isolation-ui-limit-range"
          />
          <PodSecurity info={info} />
        </div>
      )}
    </div>
  );
};
