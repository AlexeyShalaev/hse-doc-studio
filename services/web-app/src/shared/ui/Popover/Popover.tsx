import {
  type ComponentPropsWithoutRef,
  type ComponentRef,
  forwardRef,
} from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { clsx } from "clsx";
import { useIsPhoneWidth } from "../../lib/viewport";

// Anchored floating panel (status details, short forms, lists). Esc and an
// outside click close it and focus returns to the trigger. It is non-modal by
// default so the page stays usable; pass `modal` on the root when the content is
// a form that must trap focus until it is dismissed.
//
//   <Popover>
//     <PopoverTrigger asChild><button>…</button></PopoverTrigger>
//     <PopoverContent width={360} aria-label="…">…</PopoverContent>
//   </Popover>

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;
export const PopoverClose = PopoverPrimitive.Close;

export type PopoverContentProps = ComponentPropsWithoutRef<
  typeof PopoverPrimitive.Content
> & {
  /** Panel width in px (clamped to the viewport). Inline for the same reason as Modal. */
  width?: number;
  /**
   * Форма на телефоне. `sheet` (по умолчанию): шторка снизу на всю ширину с затемнением, как у
   * Modal; `anchored`: прежняя панель у кнопки (подсказки, которым шторка не нужна).
   */
  phoneForm?: "sheet" | "anchored";
};

export const PopoverContent = forwardRef<
  ComponentRef<typeof PopoverPrimitive.Content>,
  PopoverContentProps
>(
  (
    {
      className,
      width = 320,
      side = "bottom",
      align = "end",
      sideOffset = 6,
      collisionPadding = 8,
      phoneForm = "sheet",
      style,
      ...props
    },
    ref,
  ) => {
    const isSheet = useIsPhoneWidth() && phoneForm === "sheet";
    return (
      <>
        {isSheet && (
          <PopoverPrimitive.Portal>
            <div className="pop-scrim" aria-hidden="true" />
          </PopoverPrimitive.Portal>
        )}
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            ref={ref}
            data-form={isSheet ? "sheet" : "popover"}
            side={side}
            align={align}
            sideOffset={sideOffset}
            collisionPadding={collisionPadding}
            className={clsx(
              "pop-content overflow-hidden rounded-r-3 border border-border bg-bg-1 shadow-elev-pop outline-none",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
              className,
            )}
            style={{
              // Above Modal (101) so a popover can open inside a dialog.
              zIndex: 120,
              width,
              maxWidth: "calc(100vw - 16px)",
              maxHeight: "var(--radix-popover-content-available-height)",
              overflowY: "auto",
              ...style,
            }}
            {...props}
          />
        </PopoverPrimitive.Portal>
      </>
    );
  },
);

PopoverContent.displayName = "PopoverContent";
