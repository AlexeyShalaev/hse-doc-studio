import { Suspense, lazy, type ReactNode } from "react";
import { GuestProjectsView, useGuest } from "@features/guest-session";
import { useBootstrap } from "@entities/session";
import { loadLandingNamespace } from "@shared/lib/i18n/landingNamespace";
import { Spinner } from "@shared/ui";
import { AppTitlebar } from "@widgets/AppTitlebar";
import { showsLanding } from "./gateRedirect";

// Лендинг и его словарь грузятся только гостю на корне: вошедший и локальная Студия их не тянут.
const LandingPage = lazy(async () => {
  const [page] = await Promise.all([
    import("@pages/LandingPage"),
    loadLandingNamespace(),
  ]);
  return { default: page.LandingPage };
});

/**
 * Главная. Не вошедший без ссылки видит лендинг (если он включён), гость по
 * ссылке свои проекты, остальные обычный список проектов.
 */
export const HomeRoute = ({ welcome }: { welcome: ReactNode }) => {
  const guest = useGuest();
  const { data } = useBootstrap();
  if (data && showsLanding(data, "/")) {
    return (
      <Suspense
        fallback={
          <div
            className="flex flex-1 items-center justify-center"
            data-testid="landing-loading"
          >
            <Spinner size="lg" />
          </div>
        }
      >
        <LandingPage />
      </Suspense>
    );
  }
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
