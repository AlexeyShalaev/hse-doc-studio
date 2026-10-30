import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Spinner } from "@shared/ui";
import type { AdminQuotas, UpdateAdminQuotasRequest } from "@entities/session";
import type { Failure } from "../lib/failure";
import { fromMinutes, toMinutes } from "../lib/minutes";
import {
  Card,
  FailureNotice,
  LoadFailed,
  LoadingRow,
  PageHeader,
} from "./parts";

export type QuotasViewProps = {
  status: "loading" | "error" | "ready";
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
  const [minutes, setMinutes] = useState(
    quotas.max_duration_s === null ? "" : toMinutes(quotas.max_duration_s),
  );
  const [tried, setTried] = useState(false);

  const u = parseCount(user);
  const o = parseCount(org);
  const d = parseMinutes(minutes);
  const valid = u !== "bad" && o !== "bad" && d !== "bad";
  const dirty =
    user !== text(quotas.user_concurrent) ||
    org !== text(quotas.org_concurrent) ||
    minutes !==
      (quotas.max_duration_s === null ? "" : toMinutes(quotas.max_duration_s));

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="quotas-defaults"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (!valid || !dirty) return;
        onSave({ user_concurrent: u, org_concurrent: o, max_duration_s: d });
      }}
    >
      <div
        style={{
          display: "grid",
          gap: 16,
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
        }}
      >
        <Input
          label={t("quotas.userConcurrent.label")}
          type="number"
          min={1}
          max={MAX_CONCURRENT}
          value={user}
          hint={t("quotas.userConcurrent.hint")}
          {...(tried && u === "bad"
            ? { error: t("quotas.concurrent.invalid") }
            : {})}
          onChange={(event) => {
            setUser(event.target.value);
          }}
          data-testid="quota-concurrent"
        />
        <Input
          label={t("quotas.orgConcurrent.label")}
          type="number"
          min={1}
          max={MAX_CONCURRENT}
          value={org}
          hint={t("quotas.orgConcurrent.hint")}
          {...(tried && o === "bad"
            ? { error: t("quotas.concurrent.invalid") }
            : {})}
          onChange={(event) => {
            setOrg(event.target.value);
          }}
          data-testid="quota-org-concurrent"
        />
        <Input
          label={t("quotas.duration.label")}
          type="number"
          min={0.5}
          max={1440}
          step="any"
          value={minutes}
          hint={t("quotas.duration.hint")}
          {...(tried && d === "bad"
            ? { error: t("quotas.duration.invalid") }
            : {})}
          onChange={(event) => {
            setMinutes(event.target.value);
          }}
          data-testid="quota-duration"
        />
      </div>
      {failure && <FailureNotice failure={failure} />}
      <div className="flex items-center" style={{ gap: 10 }}>
        <Button
          type="submit"
          disabled={saving || !dirty}
          data-testid="quotas-save"
        >
          {saving && <Spinner size="sm" />}
          {t("quotas.save")}
        </Button>
        {saved && !dirty && (
          <span
            role="status"
            style={{ fontSize: 12, color: "var(--c-ok)" }}
            data-testid="quotas-saved"
          >
            {t("quotas.saved")}
          </span>
        )}
      </div>
    </form>
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
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="quotas-view"
    >
      <PageHeader title={t("quotas.title")} lead={t("quotas.lead")} />
      {status === "loading" && <LoadingRow testId="quotas-loading" />}
      {status === "error" && (
        <LoadFailed text={t("quotas.loadFailed")} onRetry={onRetry} />
      )}
      {status === "ready" && quotas && (
        <>
          <Card
            title={t("quotas.defaults.title")}
            lead={t("quotas.defaults.lead")}
          >
            <LimitsForm
              key={`${text(quotas.user_concurrent)}:${text(quotas.org_concurrent)}:${text(quotas.max_duration_s)}`}
              quotas={quotas}
              saving={saving}
              saved={saved}
              failure={failure}
              onSave={onSave}
            />
          </Card>
          <p
            style={{
              margin: 0,
              fontSize: 11.5,
              color: "var(--fg-2)",
              maxWidth: 640,
            }}
          >
            {t("quotas.note")}
          </p>
        </>
      )}
    </div>
  );
};
