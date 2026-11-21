import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useScrollHint } from "@shared/lib/scrollHint";
import { ActionMenu } from "@shared/ui";
import { useSpaceNav } from "../context/useSpaceNav";
import { CasesMenu } from "./CasesMenu";
import { InputChip } from "./InputChip";
import { MoreDialog } from "./MoreDialog";
import { SaveCaseDialog } from "./SaveCaseDialog";
import { useSituationModel } from "./useSituationModel";
import "./space-situation.css";

/**
 * Полоса «Для какого студента» (pack-studio-ux.md, 5.3): три главных условия кнопками, «Ещё N
 * условий», «Готовые случаи» и меню «Ещё». Любое условие меняется за два клика, результат
 * пересчитывается сразу. Телефон: ряд прокручивается, «Ещё» открывает шторку.
 */
export const SituationBar = () => {
  const { t } = useTranslation("packSpace");
  const model = useSituationModel();
  const nav = useSpaceNav();
  const [dialog, setDialog] = useState<"more" | "save" | null>(null);
  // Телефон: ряд прокручивается, край с продолжением затухает (mobile-layout.md, раздел 9).
  const hintRef = useScrollHint(null, "[data-none]");
  const rest = model.groups.more.length + model.groups.inert.length;
  return (
    <div
      ref={hintRef}
      className="sp-sit scroll-hint"
      role="group"
      aria-label={t("situation.title")}
      data-testid="sp-situation"
    >
      <span className="sp-sit-kicker">{t("situation.title")}</span>
      {model.status === "loading" ? (
        <span
          className="sp-sit-loading"
          aria-busy="true"
          aria-label={t("situation.loading")}
          data-testid="sp-sit-loading"
        >
          <span className="shimmer sp-sit-skeleton" />
          <span className="shimmer sp-sit-skeleton" />
          <span className="shimmer sp-sit-skeleton" />
        </span>
      ) : null}
      {model.status === "error" ? (
        <span className="sp-sit-failed" role="alert" data-testid="sp-sit-error">
          {t("situation.loadFailed")}{" "}
          <button type="button" className="sp-link" onClick={model.retry}>
            {t("situation.retry")}
          </button>
        </span>
      ) : null}
      {model.status === "ready" && model.total === 0 ? (
        <span className="sp-sit-none" data-testid="sp-sit-none">
          {t("situation.none")}
        </span>
      ) : null}
      {model.groups.shown.map((input) => (
        <InputChip key={input.id} input={input} model={model} />
      ))}
      {rest > 0 ? (
        <button
          type="button"
          className="sp-chip sp-chip-more"
          data-testid="sp-sit-more-btn"
          onClick={() => {
            setDialog("more");
          }}
        >
          {t("situation.more", { count: rest })}
        </button>
      ) : null}
      <span className="sp-sit-tools">
        <CasesMenu model={model} />
        <ActionMenu
          label={t("situation.menu.label")}
          testId="sp-sit-menu"
          items={[
            {
              id: "reset",
              label: t("situation.menu.reset"),
              disabled: !model.dirty,
              testId: "sp-sit-menu-reset",
              onSelect: model.reset,
            },
            {
              id: "save",
              label: t("situation.menu.save"),
              testId: "sp-sit-menu-save",
              onSelect: () => {
                setDialog("save");
              },
            },
            {
              id: "compare",
              label: t("situation.menu.compare"),
              testId: "sp-sit-menu-compare",
              onSelect: () => {
                nav.go({ tab: "check", extra: { compare: "1" } });
              },
            },
          ]}
        />
      </span>
      {dialog === "more" ? (
        <MoreDialog
          model={model}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
      {dialog === "save" ? (
        <SaveCaseDialog
          model={model}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
    </div>
  );
};
