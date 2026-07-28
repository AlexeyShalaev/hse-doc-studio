import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircle2,
  ImageOff,
  Pencil,
  ShieldCheck,
  ShieldOff,
  Trash2,
  Upload,
  User,
} from "lucide-react";
import {
  useDeleteSignaturePng,
  useUploadSignaturePng,
} from "@entities/signature";
import {
  useSigningIdentities,
  useUpdateSlotConfig,
  type SignMode,
} from "@entities/signing-identity";
import type {
  SignaturesStateResponse,
  SignatureSlotDefResponse,
} from "@shared/api/types";
import { env } from "@shared/config";
import { pickLocalized } from "@shared/lib";
import { SignatureEditorModal } from "./SignatureEditorModal";

export type SlotPanelProps = {
  projectId: string;
  slotDefs: readonly SignatureSlotDefResponse[];
  state: SignaturesStateResponse;
  lang: string;
  personNameForSlot: (slotId: string) => string | null;
};

const buildPngUrl = (projectId: string, pngPath: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${pngPath}`;

const SIGN_MODE_LABEL_KEY: Record<SignMode, string> = {
  image: "slotPanel.signMode.image",
  image_crypto: "slotPanel.signMode.imageCrypto",
  crypto_invisible: "slotPanel.signMode.cryptoInvisible",
  detached: "slotPanel.signMode.detached",
};

export const SlotPanel = ({
  projectId,
  slotDefs,
  state,
  lang,
  personNameForSlot,
}: SlotPanelProps) => {
  const { t } = useTranslation("signatureStamper");
  const { mutate: uploadPng, isPending: isUploading } = useUploadSignaturePng();
  const { mutate: deletePng, isPending: isDeleting } = useDeleteSignaturePng();
  const { mutate: updateSlotConfig, isPending: isUpdatingConfig } =
    useUpdateSlotConfig();
  const { data: identities } = useSigningIdentities();

  // The slot whose signature editor is open. `url` is the existing PNG loaded
  // for editing (null = empty editor: pick file / paste / drag-drop inside it).
  const [pending, setPending] = useState<{
    slotId: string;
    label: string;
    url: string | null;
  } | null>(null);

  // One entry point for everything: opens the editor, with the existing PNG
  // when there is one. All input methods (file / clipboard / drag-drop) live
  // inside the editor, so the slot row stays to a single button.
  const openEditor = (slotId: string, label: string, url: string | null) => {
    setPending({ slotId, label, url });
  };

  const handleConfirmUpload = (file: File) => {
    if (!pending) return;
    uploadPng(
      { projectId, slotId: pending.slotId, file },
      {
        onSuccess: () => {
          setPending(null);
        },
      },
    );
  };

  const handleDelete = (slotId: string, label: string) => {
    const ok = window.confirm(t("slotPanel.deleteConfirm", { label }));
    if (!ok) return;
    deletePng({ projectId, slotId });
  };

  const handleIdentityChange = (
    slotId: string,
    identityId: string,
    currentMode: SignMode,
    currentReason: string,
  ) => {
    const signingIdentityId = identityId === "" ? null : identityId;
    const signMode: SignMode = signingIdentityId
      ? currentMode === "image"
        ? "image_crypto"
        : currentMode
      : "image";
    updateSlotConfig({
      projectId,
      slotId,
      data: {
        signing_identity_id: signingIdentityId,
        sign_mode: signMode,
        sign_reason: currentReason,
      },
    });
  };

  const handleModeChange = (
    slotId: string,
    signMode: SignMode,
    identityId: string | null | undefined,
    currentReason: string,
  ) => {
    updateSlotConfig({
      projectId,
      slotId,
      data: {
        signing_identity_id: identityId ?? null,
        sign_mode: signMode,
        sign_reason: currentReason,
      },
    });
  };

  const handleReasonCommit = (
    slotId: string,
    reason: string,
    identityId: string | null,
    mode: SignMode,
  ) => {
    updateSlotConfig({
      projectId,
      slotId,
      data: {
        signing_identity_id: identityId,
        sign_mode: mode,
        sign_reason: reason,
      },
    });
  };

  return (
    <>
      <div className="card" style={{ overflow: "hidden" }}>
        {slotDefs.map((slot, i) => {
          const slotInfo = state.slots[slot.id];
          const pngPath = slotInfo?.png_path ?? null;
          const pngUrl = pngPath ? buildPngUrl(projectId, pngPath) : null;
          const hasPng = pngPath != null;
          const label = pickLocalized(slot.label, lang, slot.id);
          const personName = personNameForSlot(slot.id);
          const signedDocsCount = Object.entries(state.placements).filter(
            ([docId, slotMap]) =>
              slot.applies_to.includes(docId) && slotMap[slot.id]?.enabled,
          ).length;
          const currentIdentityId = slotInfo?.signing_identity_id ?? null;
          const currentMode: SignMode = slotInfo?.sign_mode ?? "image";
          const currentReason = slotInfo?.sign_reason ?? "";
          const hasIdentity = currentIdentityId != null;
          const identity = identities?.find(
            (id) => id.id === currentIdentityId,
          );

          return (
            <div
              key={slot.id}
              className="flex flex-col"
              style={{
                padding: "14px 18px",
                borderBottom:
                  i < slotDefs.length - 1 ? "1px solid var(--border)" : 0,
                gap: 10,
              }}
            >
              {/* ── Top row: thumbnail + name + PNG controls ── */}
              <div className="flex items-center" style={{ gap: 16 }}>
                <div
                  className="flex items-center justify-center shrink-0"
                  style={{
                    width: 56,
                    height: 40,
                    borderRadius: 6,
                    background: hasPng ? "var(--bg-0)" : "var(--bg-2)",
                    border: `1px solid ${
                      hasPng
                        ? "color-mix(in oklch, var(--c-ok) 35%, transparent)"
                        : "var(--border)"
                    }`,
                    color: "var(--fg-3)",
                    overflow: "hidden",
                  }}
                  title={
                    hasPng
                      ? t("slotPanel.thumbLoadedTitle")
                      : t("slotPanel.thumbNotLoadedTitle")
                  }
                >
                  {pngUrl ? (
                    <img
                      src={pngUrl}
                      alt={label}
                      style={{
                        maxWidth: "100%",
                        maxHeight: "100%",
                        objectFit: "contain",
                      }}
                    />
                  ) : (
                    <User size={18} />
                  )}
                </div>

                <div
                  className="flex flex-col"
                  style={{ gap: 4, flex: 1, minWidth: 0 }}
                >
                  <div
                    className="flex items-center gap-2"
                    style={{ minWidth: 0 }}
                  >
                    <strong
                      className="truncate"
                      style={{ fontSize: 13.5, color: "var(--fg-0)" }}
                    >
                      {personName ?? (
                        <span className="dim">
                          {t("slotPanel.personUnknown")}
                        </span>
                      )}
                    </strong>
                    <span className="dim shrink-0" style={{ fontSize: 11.5 }}>
                      · {label}
                    </span>
                  </div>
                  <div
                    className="flex items-center"
                    style={{ gap: 8, flexWrap: "wrap" }}
                  >
                    {hasPng ? (
                      <span
                        className="flex items-center gap-1"
                        style={{
                          fontSize: 10.5,
                          color: "var(--c-ok)",
                          fontWeight: 500,
                        }}
                      >
                        <CheckCircle2 size={11} />
                        {t("slotPanel.pngLoaded")}
                      </span>
                    ) : (
                      <span
                        className="flex items-center gap-1"
                        style={{
                          fontSize: 10.5,
                          color: "var(--c-warn)",
                          fontWeight: 500,
                        }}
                      >
                        <ImageOff size={11} />
                        {t("slotPanel.pngNotLoaded")}
                      </span>
                    )}
                    {hasPng && (
                      <span
                        className="mono dim"
                        style={{ fontSize: 10.5 }}
                        title={t("slotPanel.usageTitle")}
                      >
                        {t("slotPanel.usage", {
                          n: signedDocsCount,
                          total: slot.applies_to.length,
                        })}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center" style={{ gap: 6 }}>
                  <button
                    type="button"
                    className="btn xs"
                    disabled={isUploading || isDeleting}
                    onClick={() => {
                      openEditor(slot.id, label, pngUrl);
                    }}
                    title={t("slotPanel.editorButtonTitle")}
                  >
                    {hasPng ? <Pencil size={10} /> : <Upload size={10} />}
                    {hasPng ? t("slotPanel.edit") : t("slotPanel.addSignature")}
                  </button>
                  {hasPng && (
                    <button
                      type="button"
                      className="btn xs ghost"
                      disabled={isUploading || isDeleting}
                      onClick={() => {
                        handleDelete(slot.id, label);
                      }}
                      style={{ color: "var(--c-err)" }}
                      title={t("slotPanel.deletePngTitle")}
                    >
                      <Trash2 size={10} />
                    </button>
                  )}
                </div>
              </div>

              {/* ── Crypto row (optional signing identity + mode) ── */}
              <div
                className="flex items-center"
                style={{ gap: 8, padding: "6px 0 0", flexWrap: "wrap" }}
              >
                {hasIdentity ? (
                  <ShieldCheck
                    size={12}
                    style={{
                      color: identity?.trusted
                        ? "var(--accent)"
                        : "var(--fg-3)",
                      flexShrink: 0,
                    }}
                  />
                ) : (
                  <ShieldOff
                    size={12}
                    style={{ color: "var(--fg-3)", flexShrink: 0 }}
                  />
                )}
                <span
                  style={{ fontSize: 11, color: "var(--fg-2)", flexShrink: 0 }}
                >
                  {t("slotPanel.cryptoSignature")}
                </span>
                <select
                  style={{
                    fontSize: 11,
                    background: "var(--bg-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "2px 4px",
                    color: "var(--fg-0)",
                  }}
                  value={currentIdentityId ?? ""}
                  disabled={isUpdatingConfig}
                  onChange={(e) => {
                    handleIdentityChange(
                      slot.id,
                      e.target.value,
                      currentMode,
                      currentReason,
                    );
                  }}
                >
                  <option value="">{t("slotPanel.identityNone")}</option>
                  {(identities ?? []).map((id) => (
                    <option key={id.id} value={id.id}>
                      {id.label} ({id.subject_cn})
                    </option>
                  ))}
                </select>

                {hasIdentity && (
                  <>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--fg-2)",
                        flexShrink: 0,
                      }}
                    >
                      {t("slotPanel.mode")}
                    </span>
                    <select
                      style={{
                        fontSize: 11,
                        background: "var(--bg-2)",
                        border: "1px solid var(--border)",
                        borderRadius: 4,
                        padding: "2px 4px",
                        color: "var(--fg-0)",
                      }}
                      value={currentMode}
                      disabled={isUpdatingConfig}
                      onChange={(e) => {
                        handleModeChange(
                          slot.id,
                          e.target.value as SignMode,
                          currentIdentityId,
                          currentReason,
                        );
                      }}
                    >
                      {(
                        [
                          "image_crypto",
                          "crypto_invisible",
                          "detached",
                        ] as SignMode[]
                      ).map((m) => (
                        <option key={m} value={m}>
                          {t(SIGN_MODE_LABEL_KEY[m])}
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>

              {/* ── Reason row (PAdES "reason" — shown in Acrobat) ── */}
              {hasIdentity && (
                <div
                  className="flex items-center"
                  style={{ gap: 8, paddingLeft: 20 }}
                >
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--fg-2)",
                      flexShrink: 0,
                    }}
                  >
                    {t("slotPanel.reason")}
                  </span>
                  <input
                    key={`${slot.id}:${currentReason}`}
                    type="text"
                    defaultValue={currentReason}
                    placeholder={t("slotPanel.reasonPlaceholder")}
                    disabled={isUpdatingConfig}
                    maxLength={120}
                    onBlur={(e) => {
                      if (e.target.value !== currentReason) {
                        handleReasonCommit(
                          slot.id,
                          e.target.value,
                          currentIdentityId,
                          currentMode,
                        );
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") e.currentTarget.blur();
                    }}
                    style={{
                      flex: 1,
                      fontSize: 11,
                      background: "var(--bg-2)",
                      border: "1px solid var(--border)",
                      borderRadius: 4,
                      padding: "3px 6px",
                      color: "var(--fg-0)",
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
      {pending && (
        <SignatureEditorModal
          initialFile={null}
          initialUrl={pending.url}
          slotLabel={pending.label}
          isUploading={isUploading}
          onCancel={() => {
            setPending(null);
          }}
          onConfirm={handleConfirmUpload}
        />
      )}
    </>
  );
};
