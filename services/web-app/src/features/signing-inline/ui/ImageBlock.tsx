import { useTranslation } from "react-i18next";
import { CircleCheck, PenLine, Upload } from "lucide-react";
import { Button } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { InlineModel } from "../model/useInline";
import type { InlineUi, SigningInlineContext } from "../model/types";
import { DrawPad } from "./DrawPad";

export type BlockProps = {
  ctx: SigningInlineContext;
  ui: InlineUi;
  model: InlineModel;
};

/**
 * Подпись картинкой: сохранённая в профиле, нарисованная или загруженная (раздел 3.2).
 * В документ картинка попадает только после согласования.
 */
export const ImageBlock = ({ ctx, ui, model }: BlockProps) => {
  const { t } = useTranslation("signing");
  const ready = ctx.task.me.image_ready;
  const { busy, savedImage } = model;
  const drawing = ui.state.panel === "draw";

  return (
    <div className="sgi-block" data-testid="signing-image">
      {ready ? (
        <p className="sgi-ok" data-testid="signing-image-ready">
          <CircleCheck size="0.875rem" aria-hidden />
          {t("image.ready")}
        </p>
      ) : (
        <Notice
          tone={ui.state.nudge === "image" ? "err" : "warn"}
          text={t("image.missing")}
        />
      )}
      {!ready && savedImage && !drawing && (
        <div className="sgi-saved" data-testid="signing-image-saved">
          <img
            src={savedImage.url}
            alt={t("image.saved")}
            className="sgi-thumb"
          />
          <Button
            type="button"
            size="sm"
            disabled={busy}
            onClick={() => {
              void model.applySavedImage();
            }}
            data-testid="signing-image-use-saved"
          >
            {t("image.useSaved")}
          </Button>
        </div>
      )}
      {drawing ? (
        <DrawPad
          busy={busy}
          onCancel={() => {
            ui.patch({ panel: null });
          }}
          onDone={(png) => {
            void model.saveImage(png);
          }}
        />
      ) : (
        <div className="sgi-row">
          {ready && <span className="sgi-hint">{t("image.replace")}</span>}
          <Button
            type="button"
            size="sm"
            variant={ready || savedImage ? "secondary" : "primary"}
            disabled={busy}
            onClick={() => {
              ui.patch({ panel: "draw", failure: null, nudge: null });
            }}
            data-testid="signing-image-draw"
          >
            <PenLine size="0.8125rem" aria-hidden />
            {t("image.draw")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => {
              ui.patch({ panel: "editor", failure: null, nudge: null });
            }}
            data-testid="signing-image-upload"
          >
            <Upload size="0.8125rem" aria-hidden />
            {t("image.upload")}
          </Button>
        </div>
      )}
      <label className="sgi-check">
        <input
          type="checkbox"
          checked={ui.state.remember}
          disabled={busy}
          onChange={(event) => {
            ui.patch({ remember: event.target.checked });
          }}
          data-testid="signing-image-remember"
        />
        {t("image.remember")}
      </label>
    </div>
  );
};
