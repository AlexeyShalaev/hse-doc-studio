import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCheckService, useServices } from "../api/opsQueries";
import { useNow } from "../lib/useNow";
import { ServicesView } from "./ServicesView";
import { FailureNotice } from "./parts";
import { failureCode } from "@shared/api";
import type { Failure } from "../lib/failure";

/** Сервисы: данные с опросом раз в полминуты и проверка по кнопке. */
export const Services = () => {
  const services = useServices();
  const check = useCheckService();
  const now = useNow(10000);
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  useTranslation("adminOps");

  const status = services.isError
    ? "error"
    : services.isPending
      ? "loading"
      : "ready";
  return (
    <div className="flex flex-col" style={{ gap: 12 }}>
      {failure && <FailureNotice failure={failure} />}
      <ServicesView
        status={status}
        services={services.data ?? []}
        now={now}
        checkingId={checkingId}
        onRetry={() => void services.refetch()}
        onCheck={(service) => {
          setCheckingId(service.id);
          setFailure(null);
          check.mutate(service.id, {
            onError: (error) => {
              setFailure({ code: failureCode(error) });
            },
            onSettled: () => {
              setCheckingId(null);
            },
          });
        }}
      />
    </div>
  );
};
