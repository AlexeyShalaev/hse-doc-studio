import { OutcomeBody, type OutcomeBodyProps } from "./OutcomeBody";
import { ReferenceGate } from "./ui/ReferenceGate";

/**
 * Экран «Результат» версии шаблона. В разработке сначала подключает подмену API «на эталонах»
 * (ReferenceGate), в рабочей сборке сразу рисует экран.
 */
export const OutcomeScreen = (props: OutcomeBodyProps) => (
  <ReferenceGate>
    <OutcomeBody {...props} />
  </ReferenceGate>
);
