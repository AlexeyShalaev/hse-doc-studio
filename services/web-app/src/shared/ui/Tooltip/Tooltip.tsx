import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { clsx } from "clsx";

export type TooltipProps = {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  delayDuration?: number;
  collisionPadding?: number;
  className?: string;
};

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
            style={{ padding: "6px 12px" }}
            className={clsx(
              "z-50 overflow-hidden rounded-r-1 border border-border-strong bg-bg-3 text-2xs font-mono text-fg-0 shadow-elev-1",
              "animate-in fade-in-0 zoom-in-95",
              "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
              className,
            )}
          >
            {content}
            <TooltipPrimitive.Arrow className="fill-bg-3" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
};

Tooltip.displayName = "Tooltip";
