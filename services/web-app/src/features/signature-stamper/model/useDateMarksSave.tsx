import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ResetsSignaturesSchema, useSetDateMarks } from "@entities/signature";
import { ApiError, failureCode } from "@shared/api";
import type { PlacementResponse } from "@shared/api/types";
import { toast } from "@shared/lib";
import {
  marksOf,
  replaceMark,
  roundPlace,
  type DateMarkPlace,
  type DateMarksSave,
} from "../lib/dateMarkEdit";
import { ResetSignaturesDialog } from "../ui/ResetSignaturesDialog";

type Pending = {
  docId: string;
  slotId: string;
  body: DateMarksSave;
  names: string[];
};

export type DateMarksSaver = {
  /** Сохранить метки даты слота документа; на 409 `resets_signatures` спросить подтверждение. */
  save: (docId: string, slotId: string, body: DateMarksSave) => void;
  /** Рамку метки передвинули или растянули на превью. */
  movePlace: (
    docId: string,
    slotId: string,
    placement: PlacementResponse | undefined,
    index: number,
    place: DateMarkPlace,
  ) => void;
  /** Сохраняется ли сейчас слот документа. */
  isSaving: (docId: string, slotId: string) => boolean;
  /** Окно подтверждения сброса подписей: положить рядом с редактором. */
  dialog: ReactNode;
};

// Ответы сервера на сохранение меток, которые объясняем сами. 400 и 403 показывает общий тост
// клиента по коду, 409 он не показывает.
const OWN_CONFLICTS = new Set(["route_locked", "date_from_route"]);

/**
 * Сохранение меток даты (docs/design/signing-route.md, 14.6, 14.7): один запрос на действие,
 * список целиком. Документ под маршрутом с ЭП над зафиксированным PDF отвечает 409
 * `resets_signatures` со списком сбрасываемых подписей: окно называет их, «Сохранить» повторяет
 * запрос с `confirm_reset: true`, «Отмена» ничего не пишет.
 */
export const useDateMarksSave = (projectId: string): DateMarksSaver => {
  const { t } = useTranslation("signatureStamper");
  const mutation = useSetDateMarks();
  const [pending, setPending] = useState<Pending | null>(null);

  const send = (
    docId: string,
    slotId: string,
    body: DateMarksSave,
    confirmReset: boolean,
  ) => {
    mutation.mutate(
      {
        projectId,
        docId,
        slotId,
        body: { ...body, confirm_reset: confirmReset },
      },
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
              body,
              names: parsed.success
                ? [...new Set(parsed.data.resets.map((r) => r.name))]
                : [],
            });
            return;
          }
          setPending(null);
          if (OWN_CONFLICTS.has(code))
            toast.error(
              t("dates.failed", { reason: t(`errors:code.${code}`) }),
            );
        },
      },
    );
  };

  return {
    save: (docId, slotId, body) => {
      send(docId, slotId, body, false);
    },
    movePlace: (docId, slotId, placement, index, place) => {
      send(
        docId,
        slotId,
        { dates: replaceMark(marksOf(placement), index, roundPlace(place)) },
        false,
      );
    },
    isSaving: (docId, slotId) =>
      mutation.isPending &&
      mutation.variables.docId === docId &&
      mutation.variables.slotId === slotId,
    dialog: (
      <ResetSignaturesDialog
        isOpen={pending !== null}
        names={pending?.names ?? []}
        pending={mutation.isPending}
        onCancel={() => {
          setPending(null);
        }}
        onConfirm={() => {
          if (pending) send(pending.docId, pending.slotId, pending.body, true);
        }}
      />
    ),
  };
};
