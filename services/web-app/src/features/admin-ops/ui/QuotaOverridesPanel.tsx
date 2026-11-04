import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import type { PickerItem } from "@shared/lib";
import { Button, DataTable, Input, Picker, Section, Select } from "@shared/ui";
import { adminPickers } from "@entities/session";
import {
  QUOTA_RESOURCES,
  useDeleteQuotaOverride,
  useQuotaOverrides,
  useSetQuotaOverride,
  type AdminQuotaOverride,
  type OwnerKind,
  type QuotaResource,
} from "@entities/quota";
import { useQuantity } from "@entities/quota";
import type { Failure } from "../lib/failure";
import { FailureNotice } from "./parts";

const GIB = 1024 ** 3;
/** Какие ресурсы бывают у владельца: у человека только значения «на человека». */
export const resourcesFor = (owner: OwnerKind): QuotaResource[] =>
  QUOTA_RESOURCES.filter((r) => owner === "org" || !r.endsWith("_org"));

/** Значение переопределения словами: место в байтах, время в секундах, остальное числом. */
const useValueText = () => {
  const { t } = useTranslation("adminQuotas");
  const quantity = useQuantity();
  return (
    item: Pick<AdminQuotaOverride, "resource" | "hard_limit">,
  ): string => {
    if (item.resource === "jobs.max_duration_s")
      return t("overrides.seconds", { count: item.hard_limit });
    if (item.resource.startsWith("storage."))
      return quantity({ kind: "storage" }, item.hard_limit);
    return item.hard_limit.toLocaleString();
  };
};

const toStored = (resource: QuotaResource, text: string): number | null => {
  const n = Number(text.replace(",", "."));
  if (!Number.isFinite(n) || n <= 0) return null;
  const value = resource.startsWith("storage.")
    ? Math.round(n * GIB)
    : Math.round(n);
  return value >= 1 ? value : null;
};

/** Переопределения для людей и организаций: список, добавление и снятие. */
export const QuotaOverridesPanel = () => {
  const { t } = useTranslation("adminQuotas");
  const overrides = useQuotaOverrides();
  const setOverride = useSetQuotaOverride();
  const remove = useDeleteQuotaOverride();
  const valueText = useValueText();
  const [ownerKind, setOwnerKind] = useState<OwnerKind>("user");
  const [owner, setOwner] = useState<PickerItem | null>(null);
  const [resource, setResource] = useState<QuotaResource>("builds.month_user");
  const [value, setValue] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);

  const source = useMemo(
    () => (ownerKind === "user" ? adminPickers.users() : adminPickers.orgs()),
    [ownerKind],
  );
  const stored = toStored(resource, value);

  const columns = useMemo<ColumnDef<AdminQuotaOverride>[]>(
    () => [
      {
        id: "owner",
        header: t("overrides.columns.owner"),
        cell: ({ row }) => (
          <span>
            <strong>{row.original.owner_name}</strong>{" "}
            <span style={{ color: "var(--fg-3)", fontSize: "0.75rem" }}>
              {t(`overrides.ownerKind.${row.original.owner_kind}`)}
            </span>
          </span>
        ),
      },
      {
        id: "resource",
        header: t("overrides.columns.resource"),
        cell: ({ row }) =>
          t(`overrides.resources.${row.original.resource.replace(".", "_")}`),
      },
      {
        id: "value",
        header: t("overrides.columns.value"),
        cell: ({ row }) => (
          <span className="tabular-nums">{valueText(row.original)}</span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("overrides.remove", {
              name: row.original.owner_name,
            })}
            onClick={() => {
              setFailure(null);
              remove.mutate(
                {
                  ownerKind: row.original.owner_kind,
                  ownerId: row.original.owner_id,
                  resource: row.original.resource,
                },
                {
                  onError: (error) => setFailure({ code: failureCode(error) }),
                },
              );
            }}
          >
            <Trash2 size="0.875rem" aria-hidden="true" />
          </Button>
        ),
      },
    ],
    [t, remove, valueText],
  );

  const add = () => {
    if (!owner || stored === null) return;
    setFailure(null);
    setOverride.mutate(
      {
        owner_kind: ownerKind,
        owner_id: owner.id,
        resource,
        hard_limit: stored,
      },
      {
        onSuccess: () => {
          setValue("");
        },
        onError: (error) => {
          setFailure({ code: failureCode(error) });
        },
      },
    );
  };

  const unit = resource.startsWith("storage.")
    ? t("overrides.unit.gb")
    : resource === "jobs.max_duration_s"
      ? t("overrides.unit.s")
      : "";

  return (
    <Section
      title={t("overrides.title")}
      description={t("overrides.lead")}
      testId="quota-overrides"
    >
      <div className="ops-override-form" data-testid="override-form">
        <Select
          ariaLabel={t("overrides.ownerKind.label")}
          value={ownerKind}
          onValueChange={(next) => {
            const kind = next as OwnerKind;
            setOwnerKind(kind);
            setOwner(null);
            if (!resourcesFor(kind).includes(resource))
              setResource("builds.month_user");
          }}
          options={[
            { value: "user", label: t("overrides.ownerKind.user") },
            { value: "org", label: t("overrides.ownerKind.org") },
          ]}
        />
        <Picker
          source={source}
          value={owner}
          onChange={setOwner}
          label={t("overrides.owner")}
          placeholder={t("overrides.ownerPlaceholder")}
          testId="override-owner"
        />
        <Select
          ariaLabel={t("overrides.columns.resource")}
          value={resource}
          onValueChange={(next) => {
            setResource(next as QuotaResource);
          }}
          options={resourcesFor(ownerKind).map((r) => ({
            value: r,
            label: t(`overrides.resources.${r.replace(".", "_")}`),
          }))}
        />
        <span className="ops-unit-field">
          <Input
            type="number"
            min={0}
            step="any"
            value={value}
            aria-label={t("overrides.columns.value")}
            onChange={(event) => {
              setValue(event.target.value);
            }}
            data-testid="override-value"
          />
          {unit && <span className="ops-unit">{unit}</span>}
        </span>
        <Button
          size="sm"
          disabled={!owner || stored === null || setOverride.isPending}
          onClick={add}
          data-testid="override-add"
        >
          {t("overrides.add")}
        </Button>
      </div>
      {failure && <FailureNotice failure={failure} />}
      <DataTable
        caption={t("overrides.title")}
        columns={columns}
        data={overrides.data ?? []}
        getRowId={(row) => `${row.owner_kind}:${row.owner_id}:${row.resource}`}
        loading={overrides.isPending}
        error={overrides.isError ? t("overrides.loadFailed") : null}
        onRetry={() => void overrides.refetch()}
        emptyTitle={t("overrides.empty")}
      />
    </Section>
  );
};
