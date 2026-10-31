import { useState } from "react";
import { failureCode } from "@shared/api";
import { useQuotas, useUpdateQuotas } from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { statusOf } from "../lib/viewStatus";
import { GatewayPanel } from "./GatewayPanel";
import { QuotaOverridesPanel } from "./QuotaOverridesPanel";
import { QuotaPolicyPanel } from "./QuotaPolicyPanel";
import { QuotaUsagePanel } from "./QuotaUsagePanel";
import { QuotasView } from "./QuotasView";

/** Квоты: пределы задач, умолчания по видам ресурсов, переопределения, использование и ИИ-шлюз. */
export const Quotas = () => {
  const quotas = useQuotas();
  const update = useUpdateQuotas();
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  return (
    <div className="ops-stack" data-testid="quotas-page">
      <QuotasView
        status={statusOf(quotas)}
        quotas={quotas.data ?? null}
        saving={update.isPending}
        saved={saved}
        failure={failure}
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
      />
      <QuotaPolicyPanel />
      <QuotaOverridesPanel />
      <QuotaUsagePanel />
      <GatewayPanel />
    </div>
  );
};
