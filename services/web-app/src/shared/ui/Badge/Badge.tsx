import { cva, type VariantProps } from "class-variance-authority";
import { clsx } from "clsx";

// Метки читаются как текст: sans, а не моноширинный «вывод отладки».
const badgeVariants = cva("chip sans", {
  variants: {
    variant: {
      default: "",
      accent: "accent",
      solid: "solid",
      subtle: "subtle",
      success: "!text-c-ok !bg-c-ok-soft !border-c-ok/40",
      warning: "!text-c-warn !bg-c-warn-soft !border-c-warn/40",
      error: "!text-c-err !bg-c-err-soft !border-c-err/40",
      info: "!text-c-info !bg-c-info-soft !border-c-info/40",
    },
  },
  defaultVariants: {
    variant: "default",
  },
});

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>;

export const Badge = ({ className, variant, ...props }: BadgeProps) => {
  return (
    <span className={clsx(badgeVariants({ variant }), className)} {...props} />
  );
};

Badge.displayName = "Badge";
