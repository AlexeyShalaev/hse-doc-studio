import { useEffect, useState, type ReactNode } from "react";
import { Spinner } from "@shared/ui";
import { ensureAdminInstallLocales } from "../lib/locales";

/** Словарь грузится вместе с чанком админки; экран и галерея ждут его сами. */
export const Ready = ({ children }: { children: ReactNode }) => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    void ensureAdminInstallLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);
  if (!ready) {
    return (
      <div className="flex items-center" style={{ gap: 8 }} role="status">
        <Spinner size="sm" />
      </div>
    );
  }
  return <>{children}</>;
};
