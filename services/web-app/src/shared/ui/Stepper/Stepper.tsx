import type { ReactNode } from "react";
import { Check, X } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Spinner } from "../Spinner";

// Ordered list of steps (wizard header, sync phases). The current step carries
// aria-current="step"; the state of each step is also spelled out in visually
// hidden text so it never relies on colour alone.

export type StepState = "done" | "current" | "upcoming" | "error";

export type StepperStep = {
  id: string;
  label: string;
  /** Secondary text under the label (vertical) or hidden on narrow screens. */
  description?: string;
  /** Right-aligned detail, e.g. a percent while the step runs. */
  meta?: ReactNode;
  /** Overrides the state derived from `current`. */
  state?: StepState;
};

export type StepperProps = {
  steps: StepperStep[];
  /** Id of the step in progress; earlier steps are done, later ones upcoming. */
  current: string;
  /** Show a spinner on the current step (work in progress rather than waiting for input). */
  busy?: boolean;
  orientation?: "horizontal" | "vertical";
  /** Accessible name of the list. */
  label?: string;
  className?: string;
};

const MARK = 20;

const stateOf = (
  step: StepperStep,
  index: number,
  currentIndex: number,
): StepState =>
  step.state ??
  (index < currentIndex
    ? "done"
    : index === currentIndex
      ? "current"
      : "upcoming");

const markStyle = (
  state: StepState,
  spinning: boolean,
): React.CSSProperties => {
  const base: React.CSSProperties = {
    width: MARK,
    height: MARK,
    borderRadius: "50%",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    fontSize: 10.5,
    fontWeight: 700,
    border: "1.5px solid var(--border-strong)",
    color: "var(--fg-2)",
    background: "var(--bg-1)",
  };
  if (state === "current" && spinning)
    return { ...base, borderColor: "var(--accent)", background: "var(--bg-1)" };
  if (state === "current")
    return {
      ...base,
      borderColor: "var(--accent)",
      color: "var(--accent-ink)",
      background: "var(--accent)",
    };
  if (state === "done")
    return {
      ...base,
      borderColor: "var(--c-ok)",
      color: "var(--c-ok)",
      background: "var(--c-ok-soft)",
    };
  if (state === "error")
    return {
      ...base,
      borderColor: "var(--c-err)",
      color: "var(--c-err)",
      background: "var(--c-err-soft)",
    };
  return base;
};

export const Stepper = ({
  steps,
  current,
  busy = false,
  orientation = "horizontal",
  label,
  className,
}: StepperProps) => {
  const { t } = useTranslation("uiPrimitives");
  const currentIndex = Math.max(
    0,
    steps.findIndex((s) => s.id === current),
  );
  const vertical = orientation === "vertical";

  return (
    <ol
      aria-label={label}
      className={clsx(className)}
      style={{
        listStyle: "none",
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: vertical ? "column" : "row",
        gap: vertical ? 10 : 8,
        alignItems: vertical ? "stretch" : "center",
      }}
    >
      {steps.map((step, index) => {
        const state = stateOf(step, index, currentIndex);
        const spinning = busy && state === "current";
        return (
          <li
            key={step.id}
            aria-current={state === "current" ? "step" : undefined}
            data-state={state}
            style={{
              display: "flex",
              alignItems: vertical ? "flex-start" : "center",
              gap: 8,
              minWidth: 0,
              flex: vertical
                ? undefined
                : index === steps.length - 1
                  ? "0 0 auto"
                  : 1,
            }}
          >
            <span style={markStyle(state, spinning)} aria-hidden="true">
              {spinning ? (
                <Spinner size="sm" />
              ) : state === "done" ? (
                <Check size={12} strokeWidth={3} />
              ) : state === "error" ? (
                <X size={12} strokeWidth={3} />
              ) : (
                index + 1
              )}
            </span>
            <span
              className="flex flex-col"
              style={{ minWidth: 0, flex: vertical ? 1 : undefined }}
            >
              <span
                className="truncate"
                style={{
                  fontSize: 12.5,
                  fontWeight: state === "current" ? 600 : 500,
                  color: state === "upcoming" ? "var(--fg-2)" : "var(--fg-0)",
                }}
              >
                {step.label}
                <span className="sr-only">
                  {" — "}
                  {t(`stepper.${state}`)}
                </span>
              </span>
              {vertical && step.description && (
                <span className="dim" style={{ fontSize: 11 }}>
                  {step.description}
                </span>
              )}
            </span>
            {vertical && step.meta != null && (
              <span className="dim tnum" style={{ fontSize: 11 }}>
                {step.meta}
              </span>
            )}
            {!vertical && index < steps.length - 1 && (
              <span
                aria-hidden="true"
                style={{
                  flex: 1,
                  height: 1.5,
                  minWidth: 12,
                  background:
                    index < currentIndex
                      ? "var(--c-ok)"
                      : "var(--border-strong)",
                }}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
};

Stepper.displayName = "Stepper";
