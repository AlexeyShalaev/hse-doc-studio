import { useTranslation } from "react-i18next";
import { SignatureEditorModal } from "@features/signature-stamper";
import { Notice } from "@shared/ui/ConflictKit";
import { failureText } from "../lib/failureText";
import { PRIMARY_LABEL_KEY } from "../model/inlinePlan";
import { useInline } from "../model/useInline";
import type { InlineUi, SigningInlineContext } from "../model/types";
import { CryptoProDialog } from "./CryptoProDialog";
import { EsignBlock } from "./EsignBlock";
import { ImageBlock } from "./ImageBlock";
import { PassphraseDialog } from "./PassphraseDialog";
import "./signingInline.css";

/**
 * «Как подписать» на странице подписанта (docs/design/signing-route.md, 3.2): способ из
 * разрешённых точкой, картинка или ЭП. Всё делается здесь, без настроек профиля.
 */
export const SignMethodCard = ({
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
  const { failure, prompt, panel } = ui.state;
  const block = { ctx, ui, model };
  const submitLabel = t(PRIMARY_LABEL_KEY[plan.label]);
  // Отказ согласия и подписи показывает страница; в открытом окне он нужен рядом с полем.
  const pageError = ctx.failure ? t(`failure.${ctx.failure}`) : null;
  const ownError = failure ? failureText(t, failure) : null;
  const closePrompt = () => {
    ui.patch({ prompt: null, failure: null });
  };

  return (
    <section
      className="sgi-card"
      id="signing-method"
      data-testid="signing-method"
    >
      <h3>{t("method.title")}</h3>
      {plan.methods.length > 1 && (
        <div
          className="seg seg-fill"
          role="radiogroup"
          aria-label={t("method.choose")}
          data-testid="signing-method-choice"
        >
          {plan.methods.map((method) => (
            <button
              key={method}
              type="button"
              role="radio"
              aria-checked={plan.method === method}
              className={plan.method === method ? "active" : undefined}
              disabled={model.busy}
              onClick={() => {
                ui.patch({
                  method,
                  panel: null,
                  nudge: null,
                  failure: null,
                  moreOpen: false,
                });
              }}
              data-testid={`signing-method-${method}`}
            >
              {t(`method.pick.${method}`)}
            </button>
          ))}
        </div>
      )}
      {plan.block === "image" ? (
        <ImageBlock {...block} />
      ) : (
        <EsignBlock {...block} plan={plan} />
      )}
      {ownError && prompt === null && (
        <div data-testid="signing-inline-failure" data-code={failure?.code}>
          <Notice tone="err" role="alert" text={ownError} />
        </div>
      )}
      {panel === "editor" && (
        <SignatureEditorModal
          initialFile={null}
          slotLabel={t("image.editorTitle")}
          isUploading={model.busy}
          onCancel={() => {
            ui.patch({ panel: null });
          }}
          onConfirm={(file) => {
            void model.saveImage(file);
          }}
        />
      )}
      {prompt === "passphrase" && plan.key && (
        <PassphraseDialog
          open
          busy={model.busy}
          keyLabel={plan.key.label}
          submitLabel={submitLabel}
          error={ownError ?? pageError}
          onClose={closePrompt}
          onSubmit={(passphrase) => {
            void model.signWithKey(plan, passphrase);
          }}
        />
      )}
      {(prompt === "cryptopro-sign" || prompt === "cryptopro-plate") && (
        <CryptoProDialog
          purpose={prompt === "cryptopro-plate" ? "plate" : "sign"}
          busy={model.busy}
          submitLabel={submitLabel}
          error={ownError}
          onClose={closePrompt}
          onPick={(api, thumbprint) => {
            void (prompt === "cryptopro-plate"
              ? model.plateFromCryptoPro(api, thumbprint)
              : model.signWithCryptoPro(api, thumbprint));
          }}
        />
      )}
    </section>
  );
};
