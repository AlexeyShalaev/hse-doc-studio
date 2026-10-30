import { useState } from "react";
import { Lock, Pencil, Plus, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Input, Spinner } from "@shared/ui";
import type {
  AdminQuotaOverride,
  AdminQuotas,
  UpdateAdminQuotasRequest,
} from "@entities/session";
import type { Failure } from "../lib/failure";
import { fromMinutes, toMinutes } from "../lib/minutes";
import {
  Card,
  EmptyBlock,
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
  /** Организации, для которых ещё можно завести переопределение. */
  canAddOverride: boolean;
  onRetry?: () => void;
  onSave: (body: UpdateAdminQuotasRequest) => void;
  onAddOverride: () => void;
  onEditOverride: (override: AdminQuotaOverride) => void;
  onClearOverride: (override: AdminQuotaOverride) => void;
};

const SourceChip = ({
  locked,
  source,
}: {
  locked: boolean;
  source: string;
}) => {
  const { t } = useTranslation("adminOps");
  return locked ? (
    <Badge variant="subtle" style={{ gap: 4 }}>
      <Lock size={11} aria-hidden="true" />
      {t("quotas.lockedByEnv")}
    </Badge>
  ) : source === "admin" ? (
    <Badge variant="info">{t("quotas.sourceAdmin")}</Badge>
  ) : (
    <Badge variant="subtle">{t("quotas.sourceDefault")}</Badge>
  );
};

const DefaultsForm = ({
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
  const [concurrent, setConcurrent] = useState(String(quotas.jobs_concurrent));
  const [minutes, setMinutes] = useState(toMinutes(quotas.jobs_max_duration_s));
  const [tried, setTried] = useState(false);

  const cLocked = quotas.fields.jobs_concurrent?.locked === true;
  const dLocked = quotas.fields.jobs_max_duration_s?.locked === true;

  const c = Number(concurrent);
  const cValid = Number.isInteger(c) && c >= 1 && c <= 64;
  const seconds = fromMinutes(minutes);
  const dValid = seconds !== null && seconds >= 30 && seconds <= 86400;

  const cChanged = cValid && c !== quotas.jobs_concurrent;
  const dChanged = dValid && seconds !== quotas.jobs_max_duration_s;
  const changed = (cChanged && !cLocked) || (dChanged && !dLocked);
  // Пока в полях есть правка (даже неверная), кнопка живая: ошибка показывается по нажатию.
  const dirty =
    (!cLocked && concurrent !== String(quotas.jobs_concurrent)) ||
    (!dLocked && minutes !== toMinutes(quotas.jobs_max_duration_s));

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="quotas-defaults"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (!cValid || !dValid || !changed) return;
        onSave({
          jobs_concurrent: cChanged && !cLocked ? c : null,
          jobs_max_duration_s: dChanged && !dLocked ? seconds : null,
        });
      }}
    >
      <div
        style={{
          display: "grid",
          gap: 16,
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
        }}
      >
        <div className="flex flex-col" style={{ gap: 6 }}>
          <Input
            label={t("quotas.concurrent.label")}
            type="number"
            min={1}
            max={64}
            value={concurrent}
            disabled={cLocked}
            hint={t("quotas.concurrent.hint")}
            {...(tried && !cValid
              ? { error: t("quotas.concurrent.invalid") }
              : {})}
            onChange={(event) => {
              setConcurrent(event.target.value);
            }}
            data-testid="quota-concurrent"
          />
          <SourceChip
            locked={cLocked}
            source={quotas.fields.jobs_concurrent?.source ?? "default"}
          />
        </div>
        <div className="flex flex-col" style={{ gap: 6 }}>
          <Input
            label={t("quotas.duration.label")}
            type="number"
            min={0.5}
            max={1440}
            step="any"
            value={minutes}
            disabled={dLocked}
            hint={t("quotas.duration.hint")}
            {...(tried && !dValid
              ? { error: t("quotas.duration.invalid") }
              : {})}
            onChange={(event) => {
              setMinutes(event.target.value);
            }}
            data-testid="quota-duration"
          />
          <SourceChip
            locked={dLocked}
            source={quotas.fields.jobs_max_duration_s?.source ?? "default"}
          />
        </div>
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
        {saved && !changed && (
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

/** Квоты на задачи: значения установки и переопределения организаций. */
export const QuotasView = ({
  status,
  quotas,
  saving = false,
  saved = false,
  failure = null,
  canAddOverride,
  onRetry,
  onSave,
  onAddOverride,
  onEditOverride,
  onClearOverride,
}: QuotasViewProps) => {
  const { t } = useTranslation("adminOps");
  const val = (v: number | null, kind: "n" | "min"): string =>
    v === null
      ? t("quotas.overrides.inherit")
      : kind === "n"
        ? String(v)
        : t("quotas.minutes", { value: toMinutes(v) });

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
            <DefaultsForm
              key={`${String(quotas.jobs_concurrent)}:${String(quotas.jobs_max_duration_s)}`}
              quotas={quotas}
              saving={saving}
              saved={saved}
              failure={failure}
              onSave={onSave}
            />
          </Card>
          <Card
            title={t("quotas.overrides.title")}
            lead={t("quotas.overrides.lead")}
            testId="quota-overrides"
            action={
              <Button
                size="sm"
                type="button"
                disabled={!canAddOverride}
                style={{ gap: 6 }}
                onClick={onAddOverride}
                data-testid="override-add"
              >
                <Plus size={14} aria-hidden="true" />
                {t("quotas.overrides.add")}
              </Button>
            }
          >
            {quotas.overrides.length === 0 ? (
              <EmptyBlock
                testId="overrides-empty"
                title={t("quotas.overrides.empty.title")}
                body={t("quotas.overrides.empty.body")}
              />
            ) : (
              <ul
                style={{
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                {quotas.overrides.map((o) => (
                  <li
                    key={o.org_slug}
                    className="flex items-center"
                    style={{
                      gap: 12,
                      padding: "8px 10px",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--r-2)",
                      flexWrap: "wrap",
                    }}
                    data-testid={`override-${o.org_slug}`}
                  >
                    <span
                      className="flex flex-col"
                      style={{ flex: 1, minWidth: 140 }}
                    >
                      <span style={{ fontWeight: 600, fontSize: 13 }}>
                        {o.org_name}
                      </span>
                      <span
                        className="mono"
                        style={{ fontSize: 11, color: "var(--fg-2)" }}
                      >
                        {o.org_slug}
                      </span>
                    </span>
                    <span style={{ fontSize: 12.5 }}>
                      {t("quotas.concurrent.short")}:{" "}
                      <strong>{val(o.jobs_concurrent, "n")}</strong>
                    </span>
                    <span style={{ fontSize: 12.5 }}>
                      {t("quotas.duration.short")}:{" "}
                      <strong>{val(o.jobs_max_duration_s, "min")}</strong>
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      type="button"
                      style={{ gap: 5 }}
                      data-testid={`override-edit-${o.org_slug}`}
                      onClick={() => {
                        onEditOverride(o);
                      }}
                    >
                      <Pencil size={13} aria-hidden="true" />
                      {t("quotas.overrides.edit")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      type="button"
                      style={{ gap: 5 }}
                      data-testid={`override-clear-${o.org_slug}`}
                      onClick={() => {
                        onClearOverride(o);
                      }}
                    >
                      <Undo2 size={13} aria-hidden="true" />
                      {t("quotas.overrides.clear")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
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
