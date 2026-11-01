import { failureCode } from "@shared/api";
import {
  useLifecycle,
  useRunLifecycle,
  useSetRetention,
  useSetThresholds,
} from "../api/lifecycleQueries";
import { statusOf } from "../lib/viewStatus";
import { DataLifecycleView } from "./DataLifecycleView";

/** Контейнер страницы «Хранение данных»: запросы и мутации, показ в виде. */
export const DataLifecycle = () => {
  const overview = useLifecycle();
  const setRetention = useSetRetention();
  const setThresholds = useSetThresholds();
  const run = useRunLifecycle();
  const failed = [setRetention, setThresholds, run].find((m) => m.isError);
  return (
    <DataLifecycleView
      status={statusOf(overview)}
      data={overview.data ?? null}
      busyKey={
        setRetention.isPending
          ? setRetention.variables.key
          : run.isPending
            ? run.variables
            : null
      }
      failure={failed ? failureCode(failed.error) : null}
      onRetry={() => void overview.refetch()}
      onSetRetention={(key, days) => {
        setRetention.mutate({ key, days });
      }}
      onRun={(key) => {
        run.mutate(key);
      }}
      onSetThresholds={(body) => {
        setThresholds.mutate(body);
      }}
    />
  );
};
