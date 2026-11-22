import { useState } from "react";
import { ChevronDown, ChevronUp, GripVertical, Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Select } from "@shared/ui";
import {
  addSlot,
  joinPrevious,
  moveSlot,
  moveStep,
  removeSlot,
  separate,
  type Steps,
} from "../lib/routeSteps";

export type StepsEditorProps = {
  steps: Steps;
  /** Слоты каталога версии в порядке объявления. */
  catalog: readonly string[];
  slotLabel: (slot: string) => string;
  disabled: boolean;
  onChange: (steps: Steps) => void;
  testId?: string;
};

type Drag = { kind: "slot"; slot: string } | { kind: "step"; index: number };

/**
 * Порядок маршрута пака (template-studio.md, 5.6): шаги карточками, внутри шага слоты
 * подписывают параллельно. Как у маршрута проекта, но без людей и статусов: слоты и
 * шаги перетаскиваются, то же есть кнопками для клавиатуры.
 */
export const StepsEditor = ({
  steps,
  catalog,
  slotLabel,
  disabled,
  onChange,
  testId,
}: StepsEditorProps) => {
  const { t } = useTranslation("packStudio");
  const [drag, setDrag] = useState<Drag | null>(null);
  const [adding, setAdding] = useState("");
  const placed = new Set(steps.flat());
  const free = catalog.filter((slot) => !placed.has(slot));

  const dropOnStep = (index: number) => {
    if (!drag) return;
    if (drag.kind === "slot") {
      onChange(moveSlot(steps, drag.slot, { step: index, newStep: false }));
    } else {
      onChange(moveStep(steps, drag.index, index));
    }
    setDrag(null);
  };

  return (
    <div className="psf-steps" data-testid={testId}>
      <ol className="psf-step-list">
        {steps.map((step, index) => (
          <li
            key={step.join("|")}
            className="psf-step"
            draggable={!disabled}
            onDragStart={(e) => {
              e.stopPropagation();
              setDrag({ kind: "step", index });
            }}
            onDragOver={(e) => {
              if (drag) e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              dropOnStep(index);
            }}
            data-testid={testId ? `${testId}-step-${String(index)}` : undefined}
          >
            <div className="psf-step-head">
              <GripVertical size="0.75rem" aria-hidden="true" />
              <span className="psf-step-num">
                {t("submission.route.step", { n: index + 1 })}
              </span>
              {step.length > 1 && (
                <span className="ps-mark">
                  {t("submission.route.parallel")}
                </span>
              )}
              <span className="psf-actions">
                <button
                  type="button"
                  className="icon-btn"
                  disabled={disabled || index === 0}
                  onClick={() => {
                    onChange(moveStep(steps, index, index - 1));
                  }}
                  aria-label={t("submission.route.stepUp")}
                  title={t("submission.route.stepUp")}
                >
                  <ChevronUp size="0.75rem" />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  disabled={disabled || index === steps.length - 1}
                  onClick={() => {
                    onChange(moveStep(steps, index, index + 1));
                  }}
                  aria-label={t("submission.route.stepDown")}
                  title={t("submission.route.stepDown")}
                >
                  <ChevronDown size="0.75rem" />
                </button>
              </span>
            </div>
            <ul className="psf-step-slots">
              {step.map((slot) => (
                <li
                  key={slot}
                  className="psf-chip"
                  draggable={!disabled}
                  onDragStart={(e) => {
                    e.stopPropagation();
                    setDrag({ kind: "slot", slot });
                  }}
                >
                  <span title={slot}>{slotLabel(slot)}</span>
                  {index > 0 && (
                    <Button
                      size="xs"
                      variant="ghost"
                      disabled={disabled}
                      onClick={() => {
                        onChange(joinPrevious(steps, slot));
                      }}
                      title={t("submission.route.joinPrevious")}
                    >
                      {t("submission.route.joinPreviousShort")}
                    </Button>
                  )}
                  {step.length > 1 && (
                    <Button
                      size="xs"
                      variant="ghost"
                      disabled={disabled}
                      onClick={() => {
                        onChange(separate(steps, slot));
                      }}
                      title={t("submission.route.separate")}
                    >
                      {t("submission.route.separateShort")}
                    </Button>
                  )}
                  <button
                    type="button"
                    className="icon-btn"
                    disabled={disabled}
                    onClick={() => {
                      onChange(removeSlot(steps, slot));
                    }}
                    aria-label={t("submission.route.removeSlot", {
                      slot: slotLabel(slot),
                    })}
                    title={t("submission.route.removeSlot", {
                      slot: slotLabel(slot),
                    })}
                  >
                    <X size="0.6875rem" />
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      {!disabled && (
        <div
          className="psf-step-new"
          onDragOver={(e) => {
            if (drag?.kind === "slot") e.preventDefault();
          }}
          onDrop={(e) => {
            e.preventDefault();
            if (drag?.kind === "slot") {
              onChange(
                moveSlot(steps, drag.slot, {
                  step: steps.length,
                  newStep: true,
                }),
              );
            }
            setDrag(null);
          }}
        >
          {free.length > 0 ? (
            <>
              <Select
                value={adding}
                onValueChange={setAdding}
                placeholder={t("submission.route.addPlaceholder")}
                ariaLabel={t("submission.route.addPlaceholder")}
                options={free.map((slot) => ({
                  value: slot,
                  label: `${slotLabel(slot)} (${slot})`,
                }))}
              />
              <Button
                size="xs"
                variant="secondary"
                disabled={adding === ""}
                onClick={() => {
                  onChange(addSlot(steps, adding));
                  setAdding("");
                }}
                data-testid={testId ? `${testId}-add` : undefined}
              >
                <Plus size="0.6875rem" />
                {t("submission.route.addStep")}
              </Button>
            </>
          ) : (
            <span className="hint">{t("submission.route.dropHere")}</span>
          )}
        </div>
      )}
    </div>
  );
};
