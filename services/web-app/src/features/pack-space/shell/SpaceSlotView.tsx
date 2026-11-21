import { Component, Suspense, type ComponentType, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

const Failed = () => {
  const { t } = useTranslation("packSpace");
  return (
    <div className="sp-slot-failed" role="alert">
      {t("shell.slotFailed")}
    </div>
  );
};

type BoundaryProps = { name: string; children: ReactNode };

/** Сбой одного слота не роняет остальные: на его месте короткое сообщение, ошибка в консоли. */
class SlotBoundary extends Component<BoundaryProps, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  override componentDidCatch(error: unknown): void {
    console.error(`Слот «${this.props.name}» не отрисовался`, error);
  }
  override render(): ReactNode {
    return this.state.failed ? <Failed /> : this.props.children;
  }
}

/** Слот в рамке: ожидание ленивого чанка и защита от сбоя. Пустой слот ничего не рисует. */
export const SpaceSlotView = ({
  name,
  component: Slot,
}: {
  name: string;
  component: ComponentType | undefined;
}) =>
  Slot ? (
    <SlotBoundary name={name}>
      <Suspense fallback={null}>
        <Slot />
      </Suspense>
    </SlotBoundary>
  ) : null;
