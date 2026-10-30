import { useServices } from "../api/opsQueries";
import { ServicesView } from "./ServicesView";

/** Сервисы: данные с опросом раз в полминуты и обновление по кнопке. */
export const Services = () => {
  const services = useServices();
  const status =
    services.data !== undefined
      ? "ready"
      : services.isError
        ? "error"
        : "loading";
  return (
    <ServicesView
      status={status}
      services={services.data ?? []}
      refreshing={services.isFetching}
      onRetry={() => void services.refetch()}
      onRefresh={() => void services.refetch()}
    />
  );
};
