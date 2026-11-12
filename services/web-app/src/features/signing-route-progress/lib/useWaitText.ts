import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import type {
  ParticipantState,
  RouteWait,
  WaitPerson,
} from "@entities/signing-route";
import { endSentence } from "@shared/lib";
import { usePersonaLabel } from "./usePersonaLabel";

type Named = {
  name: string | null;
  cardName: string | null;
  persona: string;
  state: ParticipantState;
};

/**
 * Как назвать человека маршрута. Приглашённого Студия знает по маске почты, а автор знает его по
 * карточке проекта: имя оттуда главное, маска только подсказка. У участника с аккаунтом имя аккаунта.
 */
export const displayName = (
  person: Named,
): { name: string | null; hint: string | null } => {
  if (person.state === "invited") {
    const name = person.cardName ?? person.name;
    return {
      name,
      hint: person.name !== null && person.name !== name ? person.name : null,
    };
  }
  return { name: person.name ?? person.cardName, hint: null };
};

const capitalize = (text: string, lang: string): string =>
  text.charAt(0).toLocaleUpperCase(lang) + text.slice(1);

/** Тексты «почему ждём»: что с тем, кто смотрит, кого ждём сейчас, кто не принял приглашение. */
export const useWaitText = () => {
  const { t, i18n } = useTranslation("signingProgress");
  const personaLabel = usePersonaLabel();

  /** «Научный руководитель Салех Х. М.»; без роли просто имя. */
  const who = useCallback(
    (person: Named): string => {
      const role = personaLabel(person.persona);
      const { name } = displayName(person);
      if (role === null) return name ?? t("someone");
      const title = capitalize(role, i18n.language);
      return name === null ? title : `${title} ${name}`;
    },
    [personaLabel, t, i18n.language],
  );

  const list = useCallback(
    (people: WaitPerson[], total: number): string =>
      people
        .map((p) =>
          t(p.state === "invited" ? "wait.personInvited" : "wait.person", {
            who: who(p),
            step: p.step,
            total,
          }),
        )
        .join(", "),
    [t, who],
  );

  /** Что с тем, кто смотрит, и когда до него дойдёт; null, если он не участник. */
  const lead = useCallback(
    (wait: RouteWait): string | null => {
      const mine = wait.mine;
      if (mine === null) return null;
      switch (mine.kind) {
        case "act":
          return t(`wait.act.${mine.action}`);
        case "done":
          return t("wait.done");
        case "approved": {
          const people = mine.esign ? wait.beforeFreeze : wait.now;
          if (people.length === 0)
            return t(
              mine.esign ? "wait.approvedEsignNext" : "wait.approvedNext",
            );
          return t(mine.esign ? "wait.approvedEsign" : "wait.approved", {
            who: list(people, wait.stepsTotal),
          });
        }
        case "later":
          return wait.before.length === 0
            ? t("wait.laterNext", { step: mine.step, total: wait.stepsTotal })
            : t("wait.later", {
                step: mine.step,
                total: wait.stepsTotal,
                who: list(wait.before, wait.stepsTotal),
              });
      }
    },
    [t, list],
  );

  /** «Сейчас ждём: Научный руководитель, приглашение не принято.»; null, если ждать некого. */
  const now = useCallback(
    (wait: RouteWait): string | null => {
      if (wait.now.length === 0 || wait.mine?.kind === "act") return null;
      const invited = wait.now.some((p) => p.state === "invited");
      const names = wait.now.map((p) =>
        p.state === "invited" ? t("wait.nowInvited", { who: who(p) }) : who(p),
      );
      return endSentence(
        t("wait.now", { who: names.join(invited ? "; " : ", ") }),
      );
    },
    [t, who],
  );

  /** «Не приняли приглашение в проект: ...»; null, если таких нет. */
  const invited = useCallback(
    (wait: RouteWait): string | null =>
      wait.invited.length === 0
        ? null
        : endSentence(
            t("wait.invitedTitle", {
              who: wait.invited.map((p) => who(p)).join(", "),
            }),
          ),
    [t, who],
  );

  /**
   * Подсказка к слоту плана подписей, который держит маршрут: что с его подписантом. Свой слот
   * объясняется как `lead`; у сделавшего своё подсказки нет (null).
   */
  const slot = useCallback(
    (person: WaitPerson, wait: RouteWait): string | null => {
      if (person.me) return lead(wait);
      const args = {
        who: who(person),
        step: person.step,
        total: wait.stepsTotal,
      };
      switch (person.state) {
        case "done":
        case "returned":
          return null;
        case "waiting":
          return t(
            person.approved ? "wait.slot.approved" : "wait.slot.waiting",
            args,
          );
        default:
          return t(`wait.slot.${person.state}`, args);
      }
    },
    [t, who, lead],
  );

  return useMemo(
    () => ({ who, lead, now, invited, slot }),
    [who, lead, now, invited, slot],
  );
};
