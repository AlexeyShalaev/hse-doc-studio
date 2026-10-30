import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Modal, Select, Spinner } from "@shared/ui";
import type {
  AdminOrg,
  AdminQuotaOverride,
  UpdateAdminQuotasRequest,
} from "@entities/session";
import {
  useClearOverride,
  useOrgChoices,
  useQuotas,
  useSetOverride,
  useUpdateQuotas,
} from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { ConfirmDialog } from "./RunnerDialogs";
import { FailureNotice } from "./parts";
import { fromMinutes, toMinutes } from "../lib/minutes";
import { QuotasView } from "./QuotasView";

type Editing = { org: string; existing: AdminQuotaOverride | null };

export const OverrideForm = ({
  orgs,
  editing,
  pending,
  failure,
  onCancel,
  onSubmit,
}: {
  orgs: readonly Pick<AdminOrg, "slug" | "name">[];
  editing: Editing;
  pending: boolean;
  failure: Failure | null;
  onCancel: () => void;
  onSubmit: (slug: string, body: UpdateAdminQuotasRequest) => void;
}) => {
  const { t } = useTranslation("adminOps");
  const [slug, setSlug] = useState(editing.org);
  const [concurrent, setConcurrent] = useState(
    editing.existing?.jobs_concurrent?.toString() ?? "",
  );
  const [minutes, setMinutes] = useState(
    editing.existing?.jobs_max_duration_s != null
      ? toMinutes(editing.existing.jobs_max_duration_s)
      : "",
  );
  const [tried, setTried] = useState(false);

  const c = concurrent.trim() === "" ? null : Number(concurrent);
  const cValid = c === null || (Number.isInteger(c) && c >= 1 && c <= 64);
  const seconds = minutes.trim() === "" ? null : fromMinutes(minutes);
  const dValid =
    minutes.trim() === "" ||
    (seconds !== null && seconds >= 30 && seconds <= 86400);
  const empty = c === null && seconds === null;

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="override-form"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (!cValid || !dValid || empty || slug === "") return;
        onSubmit(slug, { jobs_concurrent: c, jobs_max_duration_s: seconds });
      }}
    >
      <div className="field">
        <label htmlFor="override-org">{t("quotas.overrides.form.org")}</label>
        <Select
          id="override-org"
          value={slug}
          isDisabled={editing.existing !== null}
          onValueChange={setSlug}
          options={orgs.map((o) => ({ value: o.slug, label: o.name }))}
          placeholder={t("quotas.overrides.form.orgPlaceholder")}
        />
      </div>
      <Input
        label={t("quotas.concurrent.label")}
        type="number"
        min={1}
        max={64}
        value={concurrent}
        hint={t("quotas.overrides.form.blankHint")}
        {...(tried && !cValid ? { error: t("quotas.concurrent.invalid") } : {})}
        onChange={(event) => {
          setConcurrent(event.target.value);
        }}
        data-testid="override-concurrent"
      />
      <Input
        label={t("quotas.duration.label")}
        type="number"
        min={0.5}
        max={1440}
        step="any"
        value={minutes}
        hint={t("quotas.overrides.form.blankHint")}
        {...(tried && !dValid ? { error: t("quotas.duration.invalid") } : {})}
        onChange={(event) => {
          setMinutes(event.target.value);
        }}
        data-testid="override-duration"
      />
      {tried && empty && cValid && dValid && (
        <p
          role="alert"
          style={{ margin: 0, fontSize: 12, color: "var(--c-err)" }}
        >
          {t("quotas.overrides.form.empty")}
        </p>
      )}
      {failure && <FailureNotice failure={failure} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={pending}
        >
          {t("cancel")}
        </Button>
        <Button type="submit" disabled={pending} data-testid="override-submit">
          {pending && <Spinner size="sm" />}
          {t("quotas.overrides.form.submit")}
        </Button>
      </div>
    </form>
  );
};

/** Квоты: значения установки и переопределения организаций. */
export const Quotas = () => {
  const { t } = useTranslation("adminOps");
  const quotas = useQuotas();
  const orgs = useOrgChoices();
  const update = useUpdateQuotas();
  const setOverride = useSetOverride();
  const clearOverride = useClearOverride();

  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [clearing, setClearing] = useState<AdminQuotaOverride | null>(null);

  const used = new Set(quotas.data?.overrides.map((o) => o.org_slug));
  const free = (orgs.data ?? []).filter((o) => !used.has(o.slug));
  const status = quotas.isError
    ? "error"
    : quotas.isPending
      ? "loading"
      : "ready";

  return (
    <>
      <QuotasView
        status={status}
        quotas={quotas.data ?? null}
        saving={update.isPending}
        saved={saved}
        failure={editing || clearing ? null : failure}
        canAddOverride={free.length > 0}
        onRetry={() => void quotas.refetch()}
        onSave={(body) => {
          setFailure(null);
          setSaved(false);
          update.mutate(body, {
            onSuccess: () => {
              setSaved(true);
            },
            onError: (error) => {
              setFailure({ code: failureCode(error) });
            },
          });
        }}
        onAddOverride={() => {
          setFailure(null);
          setEditing({ org: free[0]?.slug ?? "", existing: null });
        }}
        onEditOverride={(o) => {
          setFailure(null);
          setEditing({ org: o.org_slug, existing: o });
        }}
        onClearOverride={(o) => {
          setFailure(null);
          setClearing(o);
        }}
      />
      <Modal
        isOpen={editing !== null}
        onClose={() => {
          setEditing(null);
          setFailure(null);
        }}
        title={t("quotas.overrides.form.title")}
        description={t("quotas.overrides.form.lead")}
      >
        {editing && (
          <OverrideForm
            orgs={
              editing.existing
                ? [
                    {
                      slug: editing.existing.org_slug,
                      name: editing.existing.org_name,
                    },
                  ]
                : free
            }
            editing={editing}
            pending={setOverride.isPending}
            failure={failure}
            onCancel={() => {
              setEditing(null);
              setFailure(null);
            }}
            onSubmit={(slug, body) => {
              setFailure(null);
              setOverride.mutate(
                { slug, body },
                {
                  onSuccess: () => {
                    setEditing(null);
                  },
                  onError: (error) => {
                    setFailure({ code: failureCode(error) });
                  },
                },
              );
            }}
          />
        )}
      </Modal>
      <ConfirmDialog
        isOpen={clearing !== null}
        title={t("quotas.overrides.clearDialog.title")}
        body={t("quotas.overrides.clearDialog.body", {
          org: clearing?.org_name ?? "",
        })}
        confirmLabel={t("quotas.overrides.clearDialog.confirm")}
        danger
        pending={clearOverride.isPending}
        failure={failure}
        testId="override-clear-dialog"
        onClose={() => {
          setClearing(null);
          setFailure(null);
        }}
        onConfirm={() => {
          if (!clearing) return;
          setFailure(null);
          clearOverride.mutate(clearing.org_slug, {
            onSuccess: () => {
              setClearing(null);
            },
            onError: (error) => {
              setFailure({ code: failureCode(error) });
            },
          });
        }}
      />
    </>
  );
};
