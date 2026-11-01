import { useMyUsage } from "@entities/quota";
import { UsageView } from "./UsageView";

/** Раздел настроек «Использование» серверного режима. */
export const UsageSection = () => {
  const usage = useMyUsage();
  const status = usage.isPending
    ? "loading"
    : usage.isError
      ? "error"
      : "ready";
  return (
    <UsageView
      status={status}
      {...(usage.data ? { usage: usage.data } : {})}
      onRetry={() => void usage.refetch()}
    />
  );
};
