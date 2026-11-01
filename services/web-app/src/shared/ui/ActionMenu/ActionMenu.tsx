import type { ReactNode } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { MoreHorizontal } from "lucide-react";

// Действия строки таблицы, свёрнутые в «⋯». Опасные пункты отделены чертой и
// окрашены; подтверждение (ConfirmByName, Modal) показывает вызывающий.

export type ActionMenuItem = {
  id: string;
  label: string;
  icon?: ReactNode | undefined;
  onSelect: () => void;
  danger?: boolean | undefined;
  disabled?: boolean | undefined;
  testId?: string | undefined;
};

export type ActionMenuProps = {
  items: readonly ActionMenuItem[];
  /** Подпись кнопки для скринридера: «Действия с runner-1». */
  label: string;
  testId?: string | undefined;
  align?: "start" | "end" | undefined;
};

export const ActionMenu = ({
  items,
  label,
  testId,
  align = "end",
}: ActionMenuProps) => {
  const safe = items.filter((i) => !i.danger);
  const danger = items.filter((i) => i.danger);
  const render = (item: ActionMenuItem) => (
    <DropdownMenu.Item
      key={item.id}
      className="adm-menu-item"
      data-danger={item.danger ? "true" : undefined}
      disabled={item.disabled}
      data-testid={item.testId}
      onSelect={item.onSelect}
    >
      {item.icon}
      {item.label}
    </DropdownMenu.Item>
  );
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="icon-btn"
          aria-label={label}
          data-testid={testId}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="adm-menu"
          align={align}
          sideOffset={4}
          collisionPadding={8}
        >
          {safe.map(render)}
          {safe.length > 0 && danger.length > 0 && (
            <DropdownMenu.Separator className="adm-menu-sep" />
          )}
          {danger.map(render)}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
};

ActionMenu.displayName = "ActionMenu";
