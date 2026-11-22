import { useEffect } from "react";

// Команды палитры (Cmd+K) для экрана пространства Студии шаблонов (pack-studio-ux.md, 5.11).
// Палитра живёт в общей оболочке и не знает про экран пространства, а экран не знает про палитру:
// между ними событие окна. Кто слушает, тот и выполняет; без пространства на экране команда
// ничего не делает.

/** `where`: «Перейти к: пак, шаблон, версия»; `submit`: «Отправить на рассмотрение». */
export type PackStudioCommand = "where" | "submit";

const EVENT = "pack-studio-command";

export const runPackStudioCommand = (command: PackStudioCommand): void => {
  window.dispatchEvent(
    new CustomEvent<PackStudioCommand>(EVENT, { detail: command }),
  );
};

/** Подписка на команду на время жизни компонента. */
export const usePackStudioCommand = (
  command: PackStudioCommand,
  handler: () => void,
): void => {
  useEffect(() => {
    const onCommand = (event: Event): void => {
      if ((event as CustomEvent<PackStudioCommand>).detail === command) {
        handler();
      }
    };
    window.addEventListener(EVENT, onCommand);
    return () => {
      window.removeEventListener(EVENT, onCommand);
    };
  }, [command, handler]);
};
