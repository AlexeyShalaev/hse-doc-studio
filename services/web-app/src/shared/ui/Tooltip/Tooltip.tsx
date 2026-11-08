import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { clsx } from "clsx";
import { useUiVariant } from "../UiVariant";

export type TooltipProps = {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  delayDuration?: number;
  collisionPadding?: number;
  className?: string;
};

const TOOLTIP_LAYER = 200;

// eslint-disable-next-line react-refresh/only-export-components
export const TooltipProvider = TooltipPrimitive.Provider;

export const Tooltip = ({
  content,
  children,
  side = "top",
  align = "center",
  delayDuration = 400,
  collisionPadding = 8,
  className,
}: TooltipProps) => {
  // В консоли подсказка набрана обычным шрифтом, как весь её интерфейс.
  const sans = useUiVariant() === "console";
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            align={align}
            sideOffset={6}
            collisionPadding={collisionPadding}
            // Padding is set inline, not via Tailwind `px-*/py-*`: the Tailwind v4
            // PostCSS engine (used with the legacy `@tailwind` directives + `@config`)
            // does not regenerate brand-new spacing utilities on HMR, so changing the
            // class had no effect. Inline style is immune to that and always applies.
            // Слой выше окна настроек (90) и модальных окон (101-102), как у Select.
            style={
              sans
                ? {
                    zIndex: TOOLTIP_LAYER,
                    padding: "0.375rem 0.625rem",
                    maxWidth: "20rem",
                    lineHeight: 1.45,
                  }
                : { zIndex: TOOLTIP_LAYER, padding: "0.375rem 0.75rem" }
            }
            className={clsx(
              "overflow-hidden rounded-r-1 border shadow-elev-1",
              sans
                ? "border-border bg-bg-2 font-sans text-xs text-fg-1"
                : "border-border-strong bg-bg-3 text-2xs font-mono text-fg-0",
              "animate-in fade-in-0 zoom-in-95",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
              className,
            )}
          >
            {content}
            <TooltipPrimitive.Arrow
              className={sans ? "fill-bg-2" : "fill-bg-3"}
            />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
};

Tooltip.displayName = "Tooltip";
