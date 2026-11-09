import { useRef } from "react";
import { FileUp, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  profileImageUrl,
  useClearProfileImage,
  useClearProfilePublicKey,
  useSaveProfileImage,
  useSaveProfilePublicKey,
  useSignerProfile,
  type ProfilePublicKey,
} from "@entities/signer-profile";
import { Spinner } from "@shared/ui/Spinner";
import { localeTag, toast } from "@shared/lib";
import { SettingHead } from "./Setting";
import { formatFingerprint } from "./formatFingerprint";

const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(localeTag(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });

const rowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.625rem",
  padding: "0.5rem 0.625rem",
  borderRadius: "0.375rem",
  border: "1px solid var(--border)",
  background: "var(--bg-2)",
  flexWrap: "wrap",
} as const;

const hintStyle = {
  margin: 0,
  fontSize: "0.71875rem",
  color: "var(--fg-2)",
  lineHeight: 1.5,
} as const;

/** Выбор файла скрытым input: тот же файл можно выбрать повторно. */
const usePicker = (onFile: (file: File) => void) => {
  const ref = useRef<HTMLInputElement>(null);
  const input = (accept: string, testId: string) => (
    <input
      ref={ref}
      type="file"
      accept={accept}
      data-testid={testId}
      style={{ display: "none" }}
      onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) onFile(file);
      }}
    />
  );
  return { open: () => ref.current?.click(), input };
};

const KeySummary = ({ publicKey }: { publicKey: ProfilePublicKey }) => {
  const { t } = useTranslation("settings");
  const kind =
    publicKey.kind === "x509"
      ? t("signing.profile.kindX509")
      : t("signing.profile.kindOpenpgp");
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="truncate" style={{ fontSize: "0.8125rem" }}>
        {publicKey.owner || publicKey.cert_id}
      </div>
      <div style={{ fontSize: "0.6875rem", color: "var(--fg-2)" }}>
        <span>{kind}</span>
        {publicKey.cert_id && (
          <>
            <span style={{ margin: "0 0.3125rem" }}>·</span>
            <span className="mono">
              {formatFingerprint(publicKey.cert_id.replaceAll(" ", ""))}
            </span>
          </>
        )}
        {publicKey.valid_to && (
          <>
            <span style={{ margin: "0 0.3125rem" }}>·</span>
            <span>
              {t("signing.validUntil")}
              {formatDate(publicKey.valid_to)}
            </span>
          </>
        )}
      </div>
    </div>
  );
};

/**
 * Профиль подписанта (только сервер, вошедший человек): картинка подписи и
 * сертификат или открытый ключ OpenPGP для плашки, общие для всех проектов.
 * Закрытый ключ сюда не загружается: сервер отвергает такой файл.
 */
export const SignerProfileBlock = () => {
  const { t } = useTranslation("settings");
  const { data: profile, isLoading } = useSignerProfile();
  const saveImage = useSaveProfileImage();
  const clearImage = useClearProfileImage();
  const saveKey = useSaveProfilePublicKey();
  const clearKey = useClearProfilePublicKey();

  const onError = (err: Error) => toast.error(err.message);
  const imagePicker = usePicker((file) => {
    saveImage.mutate(file, {
      onSuccess: () => toast.success(t("signing.profile.imageSavedToast")),
      onError,
    });
  });
  const keyPicker = usePicker((file) => {
    saveKey.mutate(file, {
      onSuccess: () => toast.success(t("signing.profile.keySavedToast")),
      onError,
    });
  });

  const image = profile?.image ?? null;
  const publicKey = profile?.public_key ?? null;

  return (
    <div
      style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
      data-testid="signer-profile"
    >
      <SettingHead
        anchorId="signing-profile"
        title={t("signing.profile.title")}
        sub={t("signing.profile.subtitle")}
      />
      {isLoading ? (
        <Spinner size="sm" />
      ) : (
        <>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.375rem",
            }}
          >
            <strong style={{ fontSize: "0.78125rem" }}>
              {t("signing.profile.imageTitle")}
            </strong>
            <div style={rowStyle}>
              {image ? (
                <>
                  <img
                    src={profileImageUrl(image.sha256)}
                    alt={t("signing.profile.imageAlt")}
                    style={{
                      maxHeight: "3.5rem",
                      maxWidth: "14rem",
                      background: "#fff",
                      borderRadius: "0.25rem",
                    }}
                  />
                  <span
                    style={{
                      flex: 1,
                      fontSize: "0.6875rem",
                      color: "var(--fg-2)",
                    }}
                  >
                    {image.width_px && image.height_px
                      ? t("signing.profile.imageSize", {
                          width: image.width_px,
                          height: image.height_px,
                        })
                      : null}
                  </span>
                </>
              ) : (
                <span
                  style={{ flex: 1, fontSize: "0.75rem", color: "var(--fg-3)" }}
                >
                  {t("signing.profile.imageEmpty")}
                </span>
              )}
              <button
                className="btn btn-secondary"
                style={{ fontSize: "0.75rem", gap: "0.375rem" }}
                disabled={saveImage.isPending}
                onClick={imagePicker.open}
              >
                {saveImage.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <FileUp size="0.875rem" />
                )}
                {image
                  ? t("signing.profile.replace")
                  : t("signing.profile.upload")}
              </button>
              {image && (
                <button
                  className="btn btn-ghost icon"
                  title={t("signing.profile.remove")}
                  aria-label={t("signing.profile.remove")}
                  disabled={clearImage.isPending}
                  style={{ padding: "0.25rem", color: "var(--fg-2)" }}
                  onClick={() => {
                    if (!confirm(t("signing.profile.removeImageConfirm")))
                      return;
                    clearImage.mutate(undefined, {
                      onSuccess: () =>
                        toast.success(t("signing.profile.removedToast")),
                      onError,
                    });
                  }}
                >
                  <Trash2 size="0.875rem" />
                </button>
              )}
            </div>
            <p style={hintStyle}>{t("signing.profile.imageHint")}</p>
            {imagePicker.input("image/png", "signer-profile-image-input")}
          </div>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.375rem",
            }}
          >
            <strong style={{ fontSize: "0.78125rem" }}>
              {t("signing.profile.keyTitle")}
            </strong>
            <div style={rowStyle}>
              {publicKey ? (
                <KeySummary publicKey={publicKey} />
              ) : (
                <span
                  style={{ flex: 1, fontSize: "0.75rem", color: "var(--fg-3)" }}
                >
                  {t("signing.profile.keyEmpty")}
                </span>
              )}
              <button
                className="btn btn-secondary"
                style={{ fontSize: "0.75rem", gap: "0.375rem" }}
                disabled={saveKey.isPending}
                onClick={keyPicker.open}
              >
                {saveKey.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <FileUp size="0.875rem" />
                )}
                {publicKey
                  ? t("signing.profile.replace")
                  : t("signing.profile.upload")}
              </button>
              {publicKey && (
                <button
                  className="btn btn-ghost icon"
                  title={t("signing.profile.remove")}
                  aria-label={t("signing.profile.remove")}
                  disabled={clearKey.isPending}
                  style={{ padding: "0.25rem", color: "var(--fg-2)" }}
                  onClick={() => {
                    if (!confirm(t("signing.profile.removeKeyConfirm"))) return;
                    clearKey.mutate(undefined, {
                      onSuccess: () =>
                        toast.success(t("signing.profile.removedToast")),
                      onError,
                    });
                  }}
                >
                  <Trash2 size="0.875rem" />
                </button>
              )}
            </div>
            <p style={hintStyle}>{t("signing.profile.keyHint")}</p>
            {keyPicker.input(
              ".cer,.crt,.pem,.der,.asc,.gpg,.pgp",
              "signer-profile-key-input",
            )}
          </div>
        </>
      )}
    </div>
  );
};
