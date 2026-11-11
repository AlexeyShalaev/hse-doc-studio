import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { MY_RUNNER_DISK_PARAM } from "@entities/runner";
import { MyRunnersSection } from "./MyRunnersSection";

/**
 * Галерея: живой раздел, открытый по ссылке уведомления об очистке диска (?disk=…).
 * Параметр ставится в адрес галереи и снимается вместе с записью.
 */
export const OpenedFromNotice = ({ runnerId }: { runnerId: string }) => {
  const [, setParams] = useSearchParams();
  useEffect(() => {
    const put = (id: string | null) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (id) next.set(MY_RUNNER_DISK_PARAM, id);
          else next.delete(MY_RUNNER_DISK_PARAM);
          return next;
        },
        { replace: true },
      );
    };
    put(runnerId);
    return () => {
      put(null);
    };
  }, [runnerId, setParams]);
  return <MyRunnersSection />;
};
