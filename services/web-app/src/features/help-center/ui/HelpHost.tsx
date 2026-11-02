import { Suspense, lazy } from "react";
import { useHelpStore } from "@entities/help";

// Панель — отдельный чанк: пока справку ни разу не открывали, ни её код, ни карта не грузятся.
const HelpPanel = lazy(() =>
  import("./HelpPanel").then((m) => ({ default: m.HelpPanel })),
);

/** Точка монтирования панели справки в корневом макете. */
export const HelpHost = () => {
  const everOpened = useHelpStore((s) => s.everOpened);
  if (!everOpened) return null;
  return (
    <Suspense fallback={null}>
      <HelpPanel />
    </Suspense>
  );
};
