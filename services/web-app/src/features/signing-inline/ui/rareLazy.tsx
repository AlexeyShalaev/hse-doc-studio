import { Suspense, lazy, type ReactNode } from "react";
import { loadSigningRareTexts } from "@shared/lib/i18n/signingNamespace";

// Код и тексты редких частей приходят вместе: окно не покажется с ключами вместо слов.
const load = () =>
  Promise.all([import("./SigningInlineRare"), loadSigningRareTexts()]).then(
    ([m]) => m,
  );
type RareModule = Awaited<ReturnType<typeof load>>;

/** Редкая часть из ленивого чанка (SigningInlineRare-*.js); пока он грузится, на её месте пусто. */
const rare = <P extends object>(
  pick: (m: RareModule) => (props: P) => ReactNode,
) => {
  const Part = lazy(() => load().then((m) => ({ default: pick(m) })));
  const Rare = (props: P) => (
    <Suspense fallback={null}>
      <Part {...props} />
    </Suspense>
  );
  return Rare;
};

export const CryptoProDialog = rare((m) => m.CryptoProDialog);
export const DrawPad = rare((m) => m.DrawPad);
export const KeyCreateForm = rare((m) => m.KeyCreateForm);
export const KeyImportForm = rare((m) => m.KeyImportForm);
export const PassphraseDialog = rare((m) => m.PassphraseDialog);
