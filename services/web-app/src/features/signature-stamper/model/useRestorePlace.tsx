import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ResetsSignaturesSchema,
  useRestorePlacement,
} from "@entities/signature";
import { ApiError, failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { ResetSignaturesDialog } from "../ui/ResetSignaturesDialog";

type Pending = { docId: string; slotId: string; names: string[] };

export type RestorePlace = {
  /** Вернуть место и метки даты слота документа как в шаблоне; на 409 `resets_signatures` спросить. */
  restore: (docId: string, slotId: string) => void;
  /** Возвращается ли сейчас место слота документа. */
  isRestoring: (docId: string, slotId: string) => boolean;
  /** Окно подтверждения сброса подписей: положить рядом с редактором. */
  dialog: ReactNode;
};

// Отказы, которые объясняем сами: 409 общий тост клиента не показывает. Места на строке шаблона
// (15.17.14): якоря сборки неизвестны и запасного места нет, или строки в документе нет.
const OWN_CONFLICTS = new Set([
  "route_locked",
  "invalid_transition",
  "anchors_unknown",
  "anchor_missing",
]);

const RESTORE_TEXTS = {
  title: "place.confirm.title",
  text: "place.confirm.text",
  confirm: "place.confirm.save",
} as const;

/**
 * «Вернуть место из шаблона» (docs/design/signing-route.md, 15.6): место и метки даты слота
 * документа как в шаблоне, включена ли подпись, не меняется. Документ под маршрутом с ЭП над
 * зафиксированным PDF отвечает 409 `resets_signatures`: окно называет сбрасываемые подписи,
 * «Вернуть» повторяет запрос с `confirm_reset: true`, «Отмена» ничего не пишет.
 */
export const useRestorePlace = (projectId: string): RestorePlace => {
  const { t } = useTranslation("signatureStamper");
  const mutation = useRestorePlacement();
  const [pending, setPending] = useState<Pending | null>(null);

  const send = (docId: string, slotId: string, confirmReset: boolean) => {
    mutation.mutate(
      { projectId, docId, slotId, body: { confirm_reset: confirmReset } },
      {
        onSuccess: () => {
          setPending(null);
        },
        onError: (error) => {
          const code = failureCode(error);
          if (code === "resets_signatures" && !confirmReset) {
            const parsed = ResetsSignaturesSchema.safeParse(
              error instanceof ApiError ? error.data : null,
            );
            setPending({
              docId,
              slotId,
              names: parsed.success
                ? [...new Set(parsed.data.resets.map((r) => r.name))]
                : [],
            });
            return;
          }
          setPending(null);
          if (OWN_CONFLICTS.has(code))
            toast.error(
              t("place.failed", { reason: t(`errors:code.${code}`) }),
            );
        },
      },
    );
  };

  return {
    restore: (docId, slotId) => {
      send(docId, slotId, false);
    },
    isRestoring: (docId, slotId) =>
      mutation.isPending &&
      mutation.variables.docId === docId &&
      mutation.variables.slotId === slotId,
    dialog: (
      <ResetSignaturesDialog
        isOpen={pending !== null}
        names={pending?.names ?? []}
        pending={mutation.isPending}
        texts={RESTORE_TEXTS}
        onCancel={() => {
          setPending(null);
        }}
        onConfirm={() => {
          if (pending) send(pending.docId, pending.slotId, true);
        }}
      />
    ),
  };
};
