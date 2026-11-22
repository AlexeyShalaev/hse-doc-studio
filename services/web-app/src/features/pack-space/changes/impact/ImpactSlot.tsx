import { Component, lazy, Suspense, type ReactNode } from "react";
import { Spinner } from "@shared/ui";
import { loadPackOutcomeNamespace } from "@shared/lib/i18n/packOutcomeNamespace";
import type { ImpactBlockProps, ImpactReport } from "./ImpactBlock";

export type { ImpactReport };

// Блок «Что изменится у студентов» в своём чанке: грузится только вместе с открытой панелью
// «Изменения», основной чанк пространства его не несёт.
const ImpactBlock = lazy(() =>
  Promise.all([import("./ImpactBlock"), loadPackOutcomeNamespace()]).then(
    ([m]) => ({ default: m.ImpactBlock }),
  ),
);

type BoundaryProps = { onFail: () => void; children: ReactNode };

/** Чанк не загрузился: «до и после» молча пропускается, предложить изменения можно по-прежнему. */
class ImpactBoundary extends Component<BoundaryProps, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  override componentDidCatch(): void {
    this.props.onFail();
  }
  override render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}

/** Блок «до и после» с запасным видом на время загрузки и при сбое загрузки чанка. */
export const ImpactSlot = ({
  onFail,
  ...props
}: ImpactBlockProps & { onFail: () => void }) => (
  <ImpactBoundary onFail={onFail}>
    <Suspense
      fallback={
        <div className="flex justify-center" data-testid="impact-loading-chunk">
          <Spinner size="sm" />
        </div>
      }
    >
      <ImpactBlock {...props} />
    </Suspense>
  </ImpactBoundary>
);
