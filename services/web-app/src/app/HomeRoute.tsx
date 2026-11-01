import type { ReactNode } from "react";
import { GuestProjectsView, useGuest } from "@features/guest-session";
import { AppTitlebar } from "@widgets/AppTitlebar";

/** Главная: гость по ссылке видит проекты, открытые ему ссылками; остальные обычный список проектов. */
export const HomeRoute = ({ welcome }: { welcome: ReactNode }) => {
  const guest = useGuest();
  if (!guest) return welcome;
  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar projectName={null} />
      <div style={{ overflow: "auto", flex: 1 }}>
        <GuestProjectsView guest={guest} />
      </div>
    </div>
  );
};
