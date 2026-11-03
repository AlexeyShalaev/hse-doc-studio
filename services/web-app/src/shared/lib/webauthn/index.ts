// Церемонии WebAuthn (passkey). Библиотека @simplewebauthn/browser грузится лениво, отдельным
// чанком, только когда церемония действительно начинается: экран входа без passkey её не тянет.

type Options = Record<string, unknown>;
export type PasskeyResponse = Record<string, unknown>;

/** Почему церемония не дала ответа: отмена молчит, остальное показывает экран. */
export type PasskeyFailureKind =
  "cancelled" | "already_registered" | "unsupported" | "failed";

export class PasskeyCeremonyError extends Error {
  readonly kind: PasskeyFailureKind;

  constructor(kind: PasskeyFailureKind, cause?: unknown) {
    super(`passkey ceremony: ${kind}`, { cause });
    this.name = "PasskeyCeremonyError";
    this.kind = kind;
  }
}

const loadLibrary = () => import("@simplewebauthn/browser");

/** WebAuthn доступен: браузер его знает и страница открыта в защищённом контексте. */
export const supportsPasskeys = (): boolean =>
  typeof window !== "undefined" &&
  window.isSecureContext &&
  typeof window.PublicKeyCredential === "function";

/** Браузер умеет предлагать passkey в автозаполнении поля логина (conditional UI). */
export const supportsAutofill = async (): Promise<boolean> => {
  if (!supportsPasskeys()) return false;
  const check = (
    window.PublicKeyCredential as unknown as {
      isConditionalMediationAvailable?: () => Promise<boolean>;
    }
  ).isConditionalMediationAvailable;
  if (typeof check !== "function") return false;
  try {
    return await check.call(window.PublicKeyCredential);
  } catch {
    return false;
  }
};

const nameOf = (error: unknown): string => {
  if (!(error instanceof Error)) return "";
  const cause = (error as { cause?: unknown }).cause;
  return cause instanceof Error && error.name === "Error"
    ? cause.name
    : error.name;
};

export const toCeremonyError = (error: unknown): PasskeyCeremonyError => {
  if (error instanceof PasskeyCeremonyError) return error;
  const code = (error as { code?: unknown } | null)?.code;
  if (code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED") {
    return new PasskeyCeremonyError("already_registered", error);
  }
  if (code === "ERROR_CEREMONY_ABORTED") {
    return new PasskeyCeremonyError("cancelled", error);
  }
  const name = nameOf(error);
  if (name === "NotAllowedError" || name === "AbortError") {
    return new PasskeyCeremonyError("cancelled", error);
  }
  if (name === "InvalidStateError") {
    return new PasskeyCeremonyError("already_registered", error);
  }
  if (name === "NotSupportedError" || name === "SecurityError") {
    return new PasskeyCeremonyError("unsupported", error);
  }
  return new PasskeyCeremonyError("failed", error);
};

/** `navigator.credentials.create()` по параметрам сервера; ответ в JSON для POST. */
export const createPasskey = async (
  optionsJSON: Options,
): Promise<PasskeyResponse> => {
  if (!supportsPasskeys()) throw new PasskeyCeremonyError("unsupported");
  try {
    const { startRegistration } = await loadLibrary();
    const response = await startRegistration({
      optionsJSON: optionsJSON as unknown as Parameters<
        typeof startRegistration
      >[0]["optionsJSON"],
    });
    return response as unknown as PasskeyResponse;
  } catch (error) {
    throw toCeremonyError(error);
  }
};

/**
 * `navigator.credentials.get()`. С `autofill` запрос ждёт, пока человек выберет passkey в
 * подсказках поля логина; новая церемония сама отменяет ожидающую.
 */
export const getPasskey = async (
  optionsJSON: Options,
  { autofill = false }: { autofill?: boolean } = {},
): Promise<PasskeyResponse> => {
  if (!supportsPasskeys()) throw new PasskeyCeremonyError("unsupported");
  try {
    const { startAuthentication } = await loadLibrary();
    const response = await startAuthentication({
      optionsJSON: optionsJSON as unknown as Parameters<
        typeof startAuthentication
      >[0]["optionsJSON"],
      useBrowserAutofill: autofill,
    });
    return response as unknown as PasskeyResponse;
  } catch (error) {
    throw toCeremonyError(error);
  }
};

/** Отменить ожидающую церемонию (уход со страницы входа). */
export const cancelPasskeyCeremony = async (): Promise<void> => {
  const { WebAuthnAbortService } = await loadLibrary();
  WebAuthnAbortService.cancelCeremony();
};
