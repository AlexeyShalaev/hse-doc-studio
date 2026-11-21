import type { ReactNode } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, Plus } from "lucide-react";

// Выпадающая крошка («Пак», «Шаблон», «Версия»): кнопка с текущим значением и список. Клавиатура
// и фокус от меню Radix: стрелки, Enter, Esc, фокус возвращается на кнопку. Слой выше окон,
// как у ActionMenu.
const MENU_LAYER = 200;

export type CrumbItem = {
  id: string;
  label: ReactNode;
  /** Вторая строка: пометка («по умолчанию», «мои правки»). */
  hint?: ReactNode | undefined;
  /** Правее названия: состояние версии. */
  trail?: ReactNode | undefined;
  disabled?: boolean | undefined;
};

export type CrumbAction = {
  id: string;
  label: string;
  onSelect: () => void;
  /** Выделенный пункт сверху списка («Мои правки»). */
  accent?: boolean | undefined;
};

export const CrumbMenu = ({
  testId,
  label,
  title,
  trigger,
  items,
  value,
  onPick,
  top = [],
  bottom = [],
}: {
  testId: string;
  /** Подпись кнопки для скринридера, если видимого текста мало. */
  label?: string | undefined;
  title?: string | undefined;
  trigger: ReactNode;
  items: readonly CrumbItem[];
  /** Выбранный пункт. */
  value: string;
  onPick: (id: string) => void;
  /** Действия над списком (мои правки) и под ним (создать). */
  top?: readonly CrumbAction[];
  bottom?: readonly CrumbAction[];
}) => {
  const action = (item: CrumbAction, icon?: ReactNode) => (
    <DropdownMenu.Item
      key={item.id}
      className="adm-menu-item"
      data-accent={item.accent ? "true" : undefined}
      data-testid={`${testId}-${item.id}`}
      onSelect={item.onSelect}
    >
      {icon}
      {item.label}
    </DropdownMenu.Item>
  );
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="sp-crumb"
          aria-label={label}
          title={title}
          data-testid={testId}
        >
          {trigger}
          <ChevronDown size="0.75rem" aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="adm-menu sp-crumb-menu"
          data-form="menu"
          align="start"
          sideOffset={4}
          collisionPadding={8}
          style={{ zIndex: MENU_LAYER }}
        >
          {top.length > 0 && (
            <>
              {top.map((item) => action(item))}
              <DropdownMenu.Separator className="adm-menu-sep" />
            </>
          )}
          <DropdownMenu.RadioGroup value={value} onValueChange={onPick}>
            {items.map((item) => (
              <DropdownMenu.RadioItem
                key={item.id}
                value={item.id}
                disabled={item.disabled}
                className="adm-menu-item sp-crumb-item"
                data-testid={`${testId}-item-${item.id}`}
              >
                <span className="sp-crumb-item-text">
                  <span className="sp-crumb-item-label">{item.label}</span>
                  {item.hint ? (
                    <span className="sp-crumb-item-hint">{item.hint}</span>
                  ) : null}
                </span>
                {item.trail}
                <DropdownMenu.ItemIndicator className="adm-menu-check">
                  <Check size="0.875rem" aria-hidden="true" />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
          {bottom.length > 0 && (
            <>
              <DropdownMenu.Separator className="adm-menu-sep" />
              {bottom.map((item) =>
                action(item, <Plus size="0.875rem" aria-hidden="true" />),
              )}
            </>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
};
