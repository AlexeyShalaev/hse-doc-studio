import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { CheckCircle2 } from "lucide-react";
import { useUploadSignaturePng } from "@entities/signature";
import type {
  RouteParticipant,
  SigningRoutePreview,
} from "@entities/signing-route";
import {
  SignatureEditorModal,
  SignerPlateEditor,
} from "@features/signature-stamper";
import type { SignaturesStateResponse } from "@shared/api/types";
import { env } from "@shared/config";
import { toast } from "@shared/lib";
import { Notice } from "@shared/ui";

export type SenderSignatureCardProps = {
  projectId: string;
  /** Отправитель в маршруте; undefined: он не подписывает. */
  me: RouteParticipant | undefined;
  /** Номер его шага (с 1). */
  myStep: number | null;
  preview: SigningRoutePreview | undefined;
  state: SignaturesStateResponse | undefined;
  editable: boolean;
};

const Ok = ({ text }: { text: string }) => (
  <span
    className="flex items-center"
    style={{ gap: "0.375rem", fontSize: "0.75rem", color: "var(--c-ok)" }}
  >
    <CheckCircle2 size="0.8125rem" aria-hidden="true" />
    {text}
  </span>
);

/**
 * «Ваша подпись»: отправка и есть согласие отправителя, поэтому его картинка или данные плашки
 * нужны заранее. Если не готово, загрузить или нарисовать тут же.
 */
export const SenderSignatureCard = ({
  projectId,
  me,
  myStep,
  preview,
  state,
  editable,
}: SenderSignatureCardProps) => {
  const { t } = useTranslation("signingRouteEditor");
  const upload = useUploadSignaturePng();
  const [editing, setEditing] = useState(false);

  if (!me || me.assignments.length === 0) {
    return (
      <p className="dim" style={{ margin: 0, fontSize: "0.75rem" }}>
        {me ? t("mine.approverOnly") : t("mine.notInRoute")}
      </p>
    );
  }
  if (myStep !== 1) {
    return (
      <p className="dim" style={{ margin: 0, fontSize: "0.75rem" }}>
        {t("mine.laterStep", { n: myStep ?? 0 })}
      </p>
    );
  }

  const shown = preview?.participants.find((p) => p.participant_id === me.id);
  const slotIds = [...new Set(me.assignments.map((a) => a.slot_id))];
  const firstSlot = slotIds[0] ?? "";
  const png = state?.slots[firstSlot]?.png_path ?? null;
  const pngUrl =
    png === null
      ? null
      : `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/files/${png}`;

  const saveImage = async (file: File) => {
    try {
      // Один и тот же слот на нескольких документах хранит одну картинку.
      for (const slotId of slotIds)
        await upload.mutateAsync({ projectId, slotId, file });
      setEditing(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("mine.uploadFailed"));
    }
  };

  if (me.method === "image") {
    const ready = shown?.image_ready ?? false;
    return (
      <div className="flex flex-col" style={{ gap: "0.5rem" }}>
        {ready ? (
          <Ok text={t("mine.imageReady")} />
        ) : (
          <Notice tone="warn" text={t("mine.imageMissing")} />
        )}
        {editable && (
          <div>
            <button
              type="button"
              className={ready ? "btn xs" : "btn xs primary"}
              onClick={() => {
                setEditing(true);
              }}
              data-testid="route-my-image"
            >
              {ready ? t("mine.replace") : t("mine.upload")}
            </button>
          </div>
        )}
        {editing && (
          <SignatureEditorModal
            initialFile={null}
            initialUrl={pngUrl}
            slotLabel={t("mine.title")}
            isUploading={upload.isPending}
            onCancel={() => {
              setEditing(false);
            }}
            onConfirm={(file) => {
              void saveImage(file);
            }}
          />
        )}
      </div>
    );
  }

  // ЭП: плашке нужны владелец и сертификат или ключ; подпись ставится после фиксации.
  const ready = shown?.plate_ready ?? false;
  const key = preview?.sender_key ?? null;
  return (
    <div className="flex flex-col" style={{ gap: "0.5rem" }}>
      {ready ? (
        <Ok text={t("mine.plateReady")} />
      ) : (
        <Notice tone="warn" text={t("mine.plateMissing")} />
      )}
      {!ready && editable && (
        <SignerPlateEditor
          projectId={projectId}
          slotId={firstSlot}
          signer={state?.slots[firstSlot]?.signer}
          personName={me.name}
        />
      )}
      {key ? (
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("mine.key", { label: key.label, signer: key.signer })}
        </span>
      ) : (
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("mine.noKey")}{" "}
          <Link to="/settings/signing">{t("mine.keySettings")}</Link>
        </span>
      )}
    </div>
  );
};
