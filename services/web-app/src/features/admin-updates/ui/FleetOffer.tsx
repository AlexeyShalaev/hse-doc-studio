import { useState } from "react";
import { useFleetPlan } from "@features/admin-ops/api/opsQueries";
import { FleetUpgradeDialog } from "@features/admin-ops/ui/FleetUpgradeDialog";

/**
 * Предложение «Обновить все раннеры» после обновления Студии: окно появляется само, когда сервер уже на новой
 * версии, есть раннеры, которые Студия обновит сама, и предложение не отклонено для этой версии. Однажды показанное
 * окно остаётся, пока его не закроют (итог запуска не должен исчезнуть сам), и после закрытия не возвращается.
 */
export const FleetOffer = () => {
  const plan = useFleetPlan();
  const [shown, setShown] = useState(false);
  const [closed, setClosed] = useState(false);
  if (plan.data?.offer && !shown) setShown(true);
  if (!shown || closed) return null;
  return (
    <FleetUpgradeDialog
      onClose={() => {
        setClosed(true);
      }}
    />
  );
};
