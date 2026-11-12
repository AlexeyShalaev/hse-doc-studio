import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SkipForward } from "lucide-react";
import {
  useSkipSigningParticipant,
  type RouteParticipant,
  type SigningRoute,
} from "@entities/signing-route";
import { pickLocalized, toast } from "@shared/lib";
import { Modal, Spinner } from "@shared/ui";
import { skipOutlook, skipPairs } from "../lib/routeView";
import { displayName, useWaitText } from "../lib/useWaitText";
import { useErrorText } from "../model/useErrorText";

export type SkipActionProps = {
  route: SigningRoute;
  person: RouteParticipant;
};

/**
 * «Пропустить» у подписанта, все оставшиеся подписи которого на точке необязательны
 * (docs/design/signing-route.md, 13.9). Подтверждение называет по ситуации: какие подписи не
 * будут поставлены, куда пойдёт маршрут, что случится с меткой в PDF и что человек получит
 * уведомление. Ситуацию сервер отдаёт в `person.skip` (`refreezes`, `keeps_marks`).
 */
export const SkipAction = ({ route, person }: SkipActionProps) => {
  const { t, i18n } = useTranslation("signingProgress");
  const waitText = useWaitText();
  const errorText = useErrorText();
  const skip = useSkipSigningParticipant(route.project_id, route.id);
  const [isOpen, setIsOpen] = useState(false);

  const skipInfo = person.skip;
  if (skipInfo === null) return null;

  const who = (p: RouteParticipant): string =>
    waitText.who({ ...p, cardName: p.card_name });
  const name =
    displayName({ ...person, cardName: person.card_name }).name ?? who(person);
  const docName = (docId: string): string => {
    const doc = route.docs.find((d) => d.doc_id === docId);
    return doc ? pickLocalized(doc.name, i18n.language, docId) : docId;
  };
  const pairs = skipPairs(route, person);
  const outlook = skipOutlook(route, person);
  const names = (people: RouteParticipant[]) => people.map(who).join(", ");

  const onSkip = () => {
    skip.mutate(person.id, {
      onSuccess: () => {
        toast.success(t("skip.done", { who: name }));
        setIsOpen(false);
      },
      onError: (error) => {
        toast.error(errorText(error));
        setIsOpen(false);
      },
    });
  };

  return (
    <>
      <button
        type="button"
        className="btn xs ghost"
        style={{ whiteSpace: "nowrap" }}
        data-testid={`signing-skip-${person.id}`}
        onClick={() => {
          setIsOpen(true);
        }}
      >
        <SkipForward size="0.6875rem" aria-hidden="true" />
        {t("skip.action")}
      </button>
      <Modal
        isOpen={isOpen}
        onClose={() => {
          if (!skip.isPending) setIsOpen(false);
        }}
        title={t("skip.title", { who: name })}
        footer={
          <>
            <button
              type="button"
              className="btn"
              disabled={skip.isPending}
              onClick={() => {
                setIsOpen(false);
              }}
            >
              {t("skip.keep")}
            </button>
            <button
              type="button"
              className="btn primary"
              data-testid="signing-skip-confirm"
              disabled={skip.isPending}
              onClick={onSkip}
            >
              {skip.isPending && <Spinner size="sm" />}
              {t("skip.action")}
            </button>
          </>
        }
      >
        <ul
          data-testid="signing-skip-lines"
          style={{
            margin: 0,
            paddingLeft: "1.125rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.375rem",
            fontSize: "0.8125rem",
            lineHeight: 1.5,
          }}
        >
          {pairs.map((pair) => (
            <li key={`${pair.docId}:${pair.slot.slot_id}`}>
              {t("skip.unsigned", {
                slot: pickLocalized(
                  pair.slot.label,
                  i18n.language,
                  pair.slot.slot_id,
                ),
                doc: docName(pair.docId),
              })}
            </li>
          ))}
          <li>{t("skip.empty")}</li>
          <li>
            {outlook.kind === "next"
              ? t("skip.next", {
                  step: outlook.step,
                  who: names(outlook.people),
                })
              : outlook.kind === "wait"
                ? t("skip.wait", { who: names(outlook.people) })
                : t(`skip.${outlook.kind}`)}
          </li>
          {skipInfo.refreezes.map((docId) => (
            <li key={`r:${docId}`}>
              {t("skip.refreezes", { doc: docName(docId) })}
            </li>
          ))}
          {skipInfo.keeps_marks.map((docId) => (
            <li key={`k:${docId}`}>
              {t("skip.keepsMark", { doc: docName(docId) })}
            </li>
          ))}
          <li>{t("skip.notice", { who: name })}</li>
        </ul>
      </Modal>
    </>
  );
};
