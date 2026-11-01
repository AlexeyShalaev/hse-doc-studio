import { useState } from "react";
import { Check, Hourglass, ListOrdered, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  Input,
  PageHeader,
  Section,
  SettingRow,
  StickySaveBar,
} from "@shared/ui";
import type { AdminQuotas, UpdateAdminQuotasRequest } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import { fromMinutes, toMinutes } from "../lib/minutes";
import type { ViewStatus } from "../lib/viewStatus";
import { ViewState } from "./parts";

export type QuotasViewProps = {
  status: ViewStatus;
  quotas: AdminQuotas | null;
  saving?: boolean;
  saved?: boolean;
  failure?: Failure | null;
  onRetry?: () => void;
  onSave: (body: UpdateAdminQuotasRequest) => void;
};

const MAX_CONCURRENT = 1000;
const MIN_DURATION_S = 10;
const MAX_DURATION_S = 86400;

/** Пустое поле значит «без предела»; число проверяется границами сервера. */
const parseCount = (value: string): number | null | "bad" => {
  if (value.trim() === "") return null;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 && n <= MAX_CONCURRENT ? n : "bad";
};

const parseMinutes = (value: string): number | null | "bad" => {
  if (value.trim() === "") return null;
  const seconds = fromMinutes(value);
  return seconds !== null &&
    seconds >= MIN_DURATION_S &&
    seconds <= MAX_DURATION_S
    ? seconds
    : "bad";
};

const text = (value: number | null): string =>
  value === null ? "" : String(value);
const minutesText = (value: number | null): string =>
  value === null ? "" : toMinutes(value);

/** Поле числа с единицей справа: «2 задачи», «10 мин». */
const UnitField = ({
  id,
  value,
  unit,
  error,
  step,
  min,
  max,
  testId,
  label,
  onChange,
}: {
  id: string;
  value: string;
  unit: string;
  error: string | undefined;
  step?: string;
  min: number;
  max: number;
  testId: string;
  label: string;
  onChange: (value: string) => void;
}) => {
  const { t } = useTranslation("adminOps");
  return (
    <div className="flex flex-col" style={{ gap: 4, alignItems: "flex-end" }}>
      <span className="ops-unit-field">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          value={value}
          placeholder={t("quotas.unlimited")}
          aria-label={label}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            onChange(event.target.value);
          }}
          data-testid={testId}
        />
        <span className="ops-unit">{unit}</span>
      </span>
      {error && (
        <span
          role="alert"
          style={{ fontSize: 12, color: "var(--c-err)", maxWidth: 260 }}
        >
          {error}
        </span>
      )}
    </div>
  );
};

const LimitsForm = ({
  quotas,
  saving,
  saved,
  failure,
  onSave,
}: {
  quotas: AdminQuotas;
  saving: boolean;
  saved: boolean;
  failure: Failure | null;
  onSave: (body: UpdateAdminQuotasRequest) => void;
}) => {
  const { t } = useTranslation("adminOps");
  const [user, setUser] = useState(text(quotas.user_concurrent));
  const [org, setOrg] = useState(text(quotas.org_concurrent));
  const [minutes, setMinutes] = useState(minutesText(quotas.max_duration_s));
  const [tried, setTried] = useState(false);

  const u = parseCount(user);
  const o = parseCount(org);
  const d = parseMinutes(minutes);
  const valid = u !== "bad" && o !== "bad" && d !== "bad";
  const changed = [
    user !== text(quotas.user_concurrent),
    org !== text(quotas.org_concurrent),
    minutes !== minutesText(quotas.max_duration_s),
  ].filter(Boolean).length;

  const count = (value: string): number => Number(value) || 0;

  return (
    <>
      <Section
        title={t("quotas.concurrent.title")}
        description={t("quotas.concurrent.lead")}
        testId="quotas-defaults"
      >
        <SettingRow
          label={t("quotas.userConcurrent.label")}
          hint={t("quotas.userConcurrent.hint")}
          htmlFor="quota-user"
        >
          <UnitField
            id="quota-user"
            label={t("quotas.userConcurrent.label")}
            value={user}
            unit={t("quotas.tasks", { count: count(user) })}
            min={1}
            max={MAX_CONCURRENT}
            error={
              tried && u === "bad" ? t("quotas.concurrentInvalid") : undefined
            }
            onChange={setUser}
            testId="quota-concurrent"
          />
        </SettingRow>
        <SettingRow
          label={t("quotas.orgConcurrent.label")}
          hint={t("quotas.orgConcurrent.hint")}
          htmlFor="quota-org"
        >
          <UnitField
            id="quota-org"
            label={t("quotas.orgConcurrent.label")}
            value={org}
            unit={t("quotas.tasks", { count: count(org) })}
            min={1}
            max={MAX_CONCURRENT}
            error={
              tried && o === "bad" ? t("quotas.concurrentInvalid") : undefined
            }
            onChange={setOrg}
            testId="quota-org-concurrent"
          />
        </SettingRow>
      </Section>

      <Section
        title={t("quotas.duration.title")}
        description={t("quotas.duration.lead")}
        footer={
          saved && changed === 0 ? (
            <span
              role="status"
              className="flex items-center"
              style={{ gap: 6, fontSize: 12.5, color: "var(--c-ok)" }}
              data-testid="quotas-saved"
            >
              <Check size={14} aria-hidden="true" />
              {t("quotas.saved")}
            </span>
          ) : undefined
        }
      >
        <SettingRow
          label={t("quotas.duration.label")}
          hint={
            <>
              {t("quotas.duration.hint")}{" "}
              <Link to="/admin/instance" className="adm-hint-link">
                {t("quotas.duration.toInstance")}
              </Link>
            </>
          }
          htmlFor="quota-duration"
        >
          <UnitField
            id="quota-duration"
            label={t("quotas.duration.label")}
            value={minutes}
            unit={t("units.min")}
            step="any"
            min={0.5}
            max={1440}
            error={
              tried && d === "bad" ? t("quotas.duration.invalid") : undefined
            }
            onChange={setMinutes}
            testId="quota-duration"
          />
        </SettingRow>
      </Section>

      <Explainer />

      <StickySaveBar
        testId="quotas"
        dirtyCount={changed}
        busy={saving}
        error={failure ? t(failureKey(failure.code)) : null}
        onDiscard={() => {
          setUser(text(quotas.user_concurrent));
          setOrg(text(quotas.org_concurrent));
          setMinutes(minutesText(quotas.max_duration_s));
          setTried(false);
        }}
        onSave={() => {
          setTried(true);
          if (!valid || changed === 0) return;
          onSave({ user_concurrent: u, org_concurrent: o, max_duration_s: d });
        }}
      />
    </>
  );
};

/** Что происходит, когда предел исчерпан: короткие пункты без жаргона. */
const Explainer = () => {
  const { t } = useTranslation("adminOps");
  const items = [
    { icon: ListOrdered, key: "queue" },
    { icon: Hourglass, key: "timeout" },
    { icon: Users, key: "scope" },
  ] as const;
  return (
    <Section title={t("quotas.explain.title")} flush testId="quotas-explain">
      <ul className="ops-steps">
        {items.map(({ icon: Icon, key }) => (
          <li key={key}>
            <Icon size={15} aria-hidden="true" />
            <span>
              <strong>{t(`quotas.explain.${key}.title`)}</strong>
              {t(`quotas.explain.${key}.body`)}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
};

/** Квоты на задачи: пределы для человека, организации и времени задачи. */
export const QuotasView = ({
  status,
  quotas,
  saving = false,
  saved = false,
  failure = null,
  onRetry,
  onSave,
}: QuotasViewProps) => {
  const { t } = useTranslation("adminOps");
  return (
    <div className="ops-stack" data-testid="quotas-view">
      <PageHeader title={t("quotas.title")} description={t("quotas.lead")} />
      <ViewState
        status={status}
        errorText={t("quotas.loadFailed")}
        onRetry={onRetry}
        testId="quotas"
        skeleton={<QuotasSkeleton />}
      />
      {status === "ready" && quotas && (
        <LimitsForm
          key={`${text(quotas.user_concurrent)}:${text(quotas.org_concurrent)}:${text(quotas.max_duration_s)}`}
          quotas={quotas}
          saving={saving}
          saved={saved}
          failure={failure}
          onSave={onSave}
        />
      )}
    </div>
  );
};

const QuotasSkeleton = () => (
  <div className="adm-section" data-variant="card" style={{ padding: 20 }}>
    {[0, 1].map((row) => (
      <div
        key={row}
        className="flex items-center"
        style={{ gap: 24, padding: "12px 0" }}
      >
        <span className="flex flex-col" style={{ flex: 1, gap: 8 }}>
          <span className="adm-skel" style={{ width: "40%" }} />
          <span className="adm-skel" style={{ width: "70%" }} />
        </span>
        <span className="adm-skel" style={{ width: 150, height: 30 }} />
      </div>
    ))}
  </div>
);
