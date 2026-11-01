import { useServices } from "../api/opsQueries";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import { ServicesView } from "./ServicesView";

/** Сервисы: данные с опросом раз в полминуты и обновление по кнопке. */
export const Services = () => {
  const services = useServices();
  const now = useNow(5000);
  return (
    <ServicesView
      status={statusOf(services)}
      services={services.data ?? []}
      refreshing={services.isFetching}
      checkedAt={services.dataUpdatedAt || null}
      now={now}
      onRetry={() => void services.refetch()}
      onRefresh={() => void services.refetch()}
    />
  );
};
