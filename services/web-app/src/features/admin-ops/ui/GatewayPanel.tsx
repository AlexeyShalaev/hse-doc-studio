import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { useTranslation } from "react-i18next";
import { Badge, DataTable, Section } from "@shared/ui";
import { useGatewayStatus, type AdminGatewayProvider } from "@entities/quota";

const BREAKER_VARIANT = {
  closed: "success",
  half_open: "warning",
  open: "error",
} as const;

/** ИИ-шлюз: общие провайдеры, вызовы и ошибки за сутки, состояние автомата отказов. */
export const GatewayPanel = () => {
  const { t, i18n } = useTranslation("adminRunners");
  const gateway = useGatewayStatus();
  const num = (value: number) => value.toLocaleString(i18n.language);
  const columns = useMemo<ColumnDef<AdminGatewayProvider>[]>(
    () => [
      {
        id: "name",
        header: t("gateway.columns.provider"),
        cell: ({ row }) => <strong>{row.original.name}</strong>,
      },
      {
        id: "breaker",
        header: t("gateway.columns.state"),
        cell: ({ row }) => (
          <Badge variant={BREAKER_VARIANT[row.original.breaker]}>
            {t(`gateway.breaker.${row.original.breaker}`)}
          </Badge>
        ),
      },
      {
        id: "calls",
        header: t("gateway.columns.calls"),
        cell: ({ row }) => num(row.original.calls_24h),
      },
      {
        id: "errors",
        header: t("gateway.columns.errors"),
        cell: ({ row }) => num(row.original.errors_24h),
      },
      {
        id: "denied",
        header: t("gateway.columns.denied"),
        cell: ({ row }) => num(row.original.denied_24h),
      },
      {
        id: "tokens",
        header: t("gateway.columns.tokens"),
        cell: ({ row }) =>
          num(row.original.input_tokens_24h + row.original.output_tokens_24h),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, i18n.language],
  );
  return (
    <Section
      title={t("gateway.title")}
      description={t("gateway.lead")}
      testId="ai-gateway"
    >
      <DataTable
        caption={t("gateway.title")}
        columns={columns}
        data={gateway.data ?? []}
        getRowId={(row) => row.id}
        loading={gateway.isPending}
        error={gateway.isError ? t("gateway.loadFailed") : null}
        onRetry={() => void gateway.refetch()}
        emptyTitle={t("gateway.empty")}
        emptyHint={t("gateway.emptyHint")}
      />
    </Section>
  );
};
