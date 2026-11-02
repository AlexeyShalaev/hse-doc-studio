import { Suspense, lazy } from "react";
import { Spinner } from "@shared/ui/Spinner";

// Песочница с демо-проектом: отдельный чанк, в основной бандл не входит.
const DemoSandbox = lazy(() =>
  import("../demo/DemoSandbox").then((m) => ({ default: m.DemoSandbox })),
);

export const OnboardingDemoRoute = () => (
  <Suspense
    fallback={
      <div className="flex flex-1 items-center justify-center">
        <Spinner size="lg" />
      </div>
    }
  >
    <DemoSandbox />
  </Suspense>
);
