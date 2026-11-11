import { useRef, type ReactNode, type SyntheticEvent } from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, MoreHorizontal } from "lucide-react";
import { useIsPhoneWidth } from "../../lib/viewport";

// Действия строки таблицы, свёрнутые в «⋯». Опасные пункты отделены чертой и
// окрашены; подтверждение (ConfirmByName, Modal) показывает вызывающий.

// Меню уходит порталом в body: слой выше окна настроек (.settings-modal-overlay, 90)
// и модальных окон (101-102), как у Select. Иначе в «Моих раннерах» меню
// открывалось под окном настроек. Шторку на телефоне ставит index.css (120).
const ACTION_MENU_LAYER = 200;

export type ActionMenuItem = {
  id: string;
  label: string;
  icon?: ReactNode | undefined;
  onSelect: () => void;
  danger?: boolean | undefined;
  disabled?: boolean | undefined;
  testId?: string | undefined;
  /** Переключатель: пункт с галочкой (menuitemcheckbox), галочка видна, пока он включён. */
  checked?: boolean | undefined;
};

export type ActionMenuProps = {
  items: readonly ActionMenuItem[];
  /** Подпись кнопки для скринридера: «Действия с runner-1». */
  label: string;
  testId?: string | undefined;
  align?: "start" | "end" | undefined;
  /** Куда вернуть фокус после закрытия: preventDefault оставляет его там, куда увёл пункт. */
  onCloseAutoFocus?: ((event: Event) => void) | undefined;
};

export const ActionMenu = ({
  items,
  label,
  testId,
  align = "end",
  onCloseAutoFocus,
}: ActionMenuProps) => {
  // Телефон: длинное меню - шторка снизу с крупными строками (index.css, .adm-menu).
  const isSheet = useIsPhoneWidth();
  // Шторка открывается по pointerdown (так устроен Radix) и выезжает под палец. Отпускание
  // того же жеста долетает до пункта под ним, а Radix считает «нажал на кнопке, отпустил на
  // пункте» выбором. На касании click к тому же отдаётся тому, что теперь под пальцем. Пока
  // жест, открывший шторку, не закончился, её пункты его не принимают. Новый жест внутри
  // шторки и клавиатура снимают запрет сразу; клавиатурный выбор идёт как прежде.
  const openingGesture = useRef(false);
  const armOpeningGesture = () => {
    openingGesture.current = true;
    const release = () => {
      // После click этого жеста: сам click до пункта уже не дойдёт.
      window.setTimeout(() => {
        openingGesture.current = false;
      }, 0);
      window.removeEventListener("click", release, true);
      window.removeEventListener("pointercancel", release, true);
    };
    window.addEventListener("click", release, true);
    window.addEventListener("pointercancel", release, true);
  };
  const releaseOpeningGesture = () => {
    openingGesture.current = false;
  };
  const swallowOpeningGesture = (event: SyntheticEvent) => {
    // preventDefault: Radix пропускает свой обработчик (выбор пункта) у такого события.
    if (isSheet && openingGesture.current) event.preventDefault();
  };
  const safe = items.filter((i) => !i.danger);
  const danger = items.filter((i) => i.danger);
  const render = (item: ActionMenuItem) =>
    item.checked !== undefined ? (
      <DropdownMenu.CheckboxItem
        key={item.id}
        className="adm-menu-item"
        checked={item.checked}
        disabled={item.disabled}
        data-testid={item.testId}
        onSelect={item.onSelect}
        onPointerUp={swallowOpeningGesture}
        onClick={swallowOpeningGesture}
      >
        {item.icon}
        {item.label}
        <DropdownMenu.ItemIndicator className="adm-menu-check">
          <Check size="0.875rem" aria-hidden="true" />
        </DropdownMenu.ItemIndicator>
      </DropdownMenu.CheckboxItem>
    ) : (
      <DropdownMenu.Item
        key={item.id}
        className="adm-menu-item"
        data-danger={item.danger ? "true" : undefined}
        disabled={item.disabled}
        data-testid={item.testId}
        onSelect={item.onSelect}
        onPointerUp={swallowOpeningGesture}
        onClick={swallowOpeningGesture}
      >
        {item.icon}
        {item.label}
      </DropdownMenu.Item>
    );
  return (
    <DropdownMenu.Root
      modal={false}
      onOpenChange={(open) => {
        if (!open) releaseOpeningGesture();
      }}
    >
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="icon-btn"
          aria-label={label}
          data-testid={testId}
          onPointerDown={(event) => {
            // Те же условия, при которых Radix открывает меню по нажатию.
            if (isSheet && event.button === 0 && !event.ctrlKey) {
              armOpeningGesture();
            }
          }}
        >
          <MoreHorizontal size="1rem" aria-hidden="true" />
        </button>
      </DropdownMenu.Trigger>
      {isSheet && (
        <DropdownMenu.Portal>
          <div className="pop-scrim" aria-hidden="true" />
        </DropdownMenu.Portal>
      )}
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="adm-menu"
          data-form={isSheet ? "sheet" : "menu"}
          align={align}
          sideOffset={4}
          collisionPadding={8}
          onCloseAutoFocus={onCloseAutoFocus}
          onPointerDownCapture={releaseOpeningGesture}
          onKeyDownCapture={releaseOpeningGesture}
          style={{ zIndex: ACTION_MENU_LAYER }}
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
