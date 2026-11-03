import { OnboardingDemoRoute } from "@features/onboarding";
import { AppTitlebar } from "@widgets/AppTitlebar";

/** Песочница с демо-проектом онбординга (`/onboarding/demo`). */
export const OnboardingDemoPage = () => (
  <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
    <AppTitlebar />
    <OnboardingDemoRoute />
  </div>
);
