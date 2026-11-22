import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  usePackPreviewOptions,
  usePackSignatures,
  usePackSubmission,
  type OutcomeInput,
  type PackVersionRef,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { makeNaming, type Naming } from "./naming";

/**
 * Названия пака для слоя человеческих формулировок: документы, подписи и точки сдачи берутся из
 * тех же ответов, что у «Содержимого» (кэш общий), условия из ответа `inputs`. Пока ответы не
 * пришли, названия нейтральные («один из документов»), идентификаторы не показываются.
 */
export const useNaming = (
  workspaceId: string,
  ref: PackVersionRef,
  inputs: readonly OutcomeInput[] | undefined,
): Naming => {
  const { t, i18n } = useTranslation("packSpace");
  const options = usePackPreviewOptions(workspaceId, ref);
  const signatures = usePackSignatures(workspaceId, ref, null);
  const submission = usePackSubmission(workspaceId, ref);
  const lng = i18n.language;
  const documents = options.data?.documents;
  const slots = signatures.data?.slots;
  const profiles = submission.data?.profiles;
  return useMemo(
    () =>
      makeNaming({
        lng,
        t,
        documents,
        slots,
        points: profiles?.map((profile) => ({
          id: profile.id,
          name: profile.name,
        })),
        inputLabel: (id) => {
          const found = inputs?.find((item) => item.id === id);
          return found
            ? pickLocalized(found.label ?? undefined, lng, "") || null
            : null;
        },
      }),
    [lng, t, documents, slots, profiles, inputs],
  );
};
