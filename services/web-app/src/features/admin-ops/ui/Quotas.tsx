import { useState } from "react";
import { failureCode } from "@shared/api";
import { useQuotas, useUpdateQuotas } from "../api/opsQueries";
import type { Failure } from "../lib/failure";
import { QuotasView } from "./QuotasView";

/** Квоты: три предела установки, сохраняются одной формой. */
export const Quotas = () => {
  const quotas = useQuotas();
  const update = useUpdateQuotas();
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  const status = quotas.isError
    ? "error"
    : quotas.isPending
      ? "loading"
      : "ready";

  return (
    <QuotasView
      status={status}
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
  );
};
