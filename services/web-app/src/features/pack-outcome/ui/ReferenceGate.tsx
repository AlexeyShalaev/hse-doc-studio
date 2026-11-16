import { useEffect, useState, type ReactNode } from "react";
import { Spinner } from "@shared/ui";

/**
 * В разработке подключает подмену API результата «на эталонах» до первого запроса экрана; в
 * рабочей сборке ничего не делает и не тянет эталоны (ветка под import.meta.env.DEV вырезается).
 */
export const ReferenceGate = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(!import.meta.env.DEV);
  useEffect(() => {
    if (import.meta.env.DEV) {
      let live = true;
      void import("@entities/pack-studio/reference").then((reference) => {
        reference.installOutcomeReference();
        if (live) setReady(true);
      });
      return () => {
        live = false;
      };
    }
    return undefined;
  }, []);
  if (!ready) {
    return (
      <div className="po-gate">
        <Spinner size="md" />
      </div>
    );
  }
  return <>{children}</>;
};
