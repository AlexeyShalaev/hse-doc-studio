import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";
import type {
  RunnerResourcesView,
  RunnerSecurityView,
} from "@entities/session";
import { useValue } from "../lib/isolationValue";
import "./isolation.css";

/**
 * Общие куски экранов изоляции раннеров: метка источника, список фактов,
 * ресурсы и securityContext. Значение null везде значит «нет данных».
 */

export type SourceKind =
  | "runner"
  | "cluster"
  | "config"
  | "declared"
  | "checked"
  | "missing"
  | "unchecked";

const SOURCE_VARIANT = {
  runner: "info",
  cluster: "success",
  config: "subtle",
  declared: "subtle",
  checked: "success",
  missing: "warning",
  unchecked: "default",
} as const;

/** Откуда значение: из конфигурации, от раннера или проверено в кластере. */
export const SourceTag = ({
  kind,
  extra,
}: {
  kind: SourceKind;
  /** Дописка к метке, например «2 минуты назад». */
  extra?: string | null | undefined;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const label = {
    runner: t("source.runner"),
    cluster: t("source.cluster"),
    config: t("source.config"),
    declared: t("source.declared"),
    checked: t("source.checked"),
    missing: t("source.missing"),
    unchecked: t("source.unchecked"),
  }[kind];
  return (
    <Badge variant={SOURCE_VARIANT[kind]} data-source={kind}>
      {extra ? `${label}, ${extra}` : label}
    </Badge>
  );
};

export type Fact = {
  label: string;
  value: ReactNode;
  tone?: "warning" | "muted" | undefined;
  testId?: string | undefined;
};

/** Подпись и значение в две колонки; на узком экране подпись над значением. */
export const FactList = ({ items }: { items: readonly Fact[] }) => (
  <dl className="iso-facts">
    {items.map((item) => (
      <div key={item.label} style={{ display: "contents" }}>
        <dt>{item.label}</dt>
        <dd data-tone={item.tone} data-testid={item.testId}>
          {item.value}
        </dd>
      </div>
    ))}
  </dl>
);

/** Заголовок блока с меткой источника. */
export const Block = ({
  title,
  source,
  children,
  testId,
}: {
  title: ReactNode;
  source?: ReactNode;
  children: ReactNode;
  testId?: string;
}) => (
  <section className="iso-block" data-testid={testId}>
    <h3 className="iso-block-head">
      <span>{title}</span>
      {source}
    </h3>
    {children}
  </section>
);

/** requests / limits CPU, памяти и эфемерного диска. */
export const ResourceFacts = ({
  resources,
}: {
  resources: RunnerResourcesView | null;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text } = useValue();
  if (resources === null) {
    return <p className="iso-note">{t("value.none")}</p>;
  }
  // cgroup знает только лимит: пустой лимит там значит «без лимита».
  const limit = (value: string | null) =>
    value === null && resources.source === "cgroup"
      ? t("value.unlimited")
      : text(value);
  const pair = (request: string | null, limitValue: string | null) =>
    t("res.pair", { request: text(request), limit: limit(limitValue) });
  return (
    <FactList
      items={[
        {
          label: t("res.cpu"),
          value: pair(resources.cpu_request, resources.cpu_limit),
        },
        {
          label: t("res.memory"),
          value: pair(resources.memory_request, resources.memory_limit),
        },
        {
          label: t("res.ephemeral"),
          value: pair(resources.ephemeral_request, resources.ephemeral_limit),
        },
      ]}
    />
  );
};

/** Флаги securityContext; «нет» у защитного флага подсвечено. */
export const SecurityFacts = ({
  security,
}: {
  security: RunnerSecurityView | null;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  const { text, flag } = useValue();
  if (security === null) {
    return <p className="iso-note">{t("value.none")}</p>;
  }
  const guard = (label: string, value: boolean | null): Fact => ({
    label,
    value: flag(value),
    tone: value === false ? "warning" : value === null ? "muted" : undefined,
  });
  const items: Fact[] = [
    guard(t("sec.runAsNonRoot"), security.run_as_non_root),
    { label: t("sec.runAsUser"), value: text(security.run_as_user) },
    guard(t("sec.readOnlyRoot"), security.read_only_root),
    guard(t("sec.noPrivilegeEscalation"), security.no_privilege_escalation),
    guard(t("sec.seccomp"), security.seccomp),
    guard(t("sec.capabilitiesDropped"), security.capabilities_dropped),
  ];
  if (security.automount_token !== null) {
    items.push({
      label: t("sec.automountToken"),
      value: flag(security.automount_token),
    });
  }
  return <FactList items={items} />;
};

/** Ресурсы и securityContext под подзаголовками. */
export const PodFacts = ({
  resources,
  security,
}: {
  resources: RunnerResourcesView | null;
  security: RunnerSecurityView | null;
}) => {
  const { t } = useTranslation("adminRunnerIsolation");
  return (
    <>
      <p className="iso-sub" title={t("res.hint")}>
        {t("res.title")} ({t("res.hint")})
      </p>
      <ResourceFacts resources={resources} />
      <p className="iso-sub">{t("sec.title")}</p>
      <SecurityFacts security={security} />
    </>
  );
};
