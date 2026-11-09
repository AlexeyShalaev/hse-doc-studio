import { useTranslation } from "react-i18next";
import { Check, PenLine } from "lucide-react";
import { Button } from "@shared/ui";
import { PRIMARY_LABEL_KEY } from "../model/inlinePlan";
import { useInline } from "../model/useInline";
import type { InlineUi, SigningInlineContext } from "../model/types";

/**
 * Главная кнопка страницы подписанта: «Согласовать», «Согласовать и подписать» или
 * «Подписать». Если чего-то не хватает (картинки, ключа, файла подписи), нажатие
 * показывает это место в блоке «Как подписать».
 */
export const SignPrimary = ({
  ctx,
  ui,
}: {
  ctx: SigningInlineContext;
  ui: InlineUi;
}) => {
  const { t } = useTranslation("signing");
  const model = useInline(ctx, ui);
  const { plan } = model;
  if (!plan) return null;
  return (
    <Button
      type="button"
      disabled={model.busy}
      onClick={() => {
        model.runPrimary();
        if (plan.blocker !== null)
          // На телефоне блок выше кнопок: показываем, чего не хватает.
          (
            document.getElementById(
              "signing-method",
            ) as Partial<HTMLElement> | null
          )?.scrollIntoView?.({ block: "center", behavior: "smooth" });
      }}
      data-testid="signing-primary"
      data-label={plan.label}
      data-blocked={plan.blocker ?? ""}
    >
      {plan.label === "approve" ? (
        <Check size="0.875rem" aria-hidden />
      ) : (
        <PenLine size="0.875rem" aria-hidden />
      )}
      {model.busy ? t("actions.working") : t(PRIMARY_LABEL_KEY[plan.label])}
    </Button>
  );
};
