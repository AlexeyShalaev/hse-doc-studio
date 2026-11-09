import type { TFunction } from "i18next";
import type { SigningFailure } from "@entities/signing-route";

/** Текст отказа из словаря `signing`: свой у известного кода, иначе пояснение сервера. */
export const failureText = (
  t: TFunction<"signing">,
  failure: SigningFailure,
): string => {
  if (failure.code === "cryptopro")
    return t("failure.cryptopro", { detail: failure.detail ?? "" });
  if (failure.code === "unknown")
    return failure.detail
      ? t("failure.unknownDetail", { detail: failure.detail })
      : t("failure.unknown");
  return t(`failure.${failure.code}`);
};
