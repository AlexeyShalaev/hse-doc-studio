import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useProjectRoleLabel } from "@entities/project";
import {
  hasDocument,
  splitPeople,
  type PersonOnline,
  type ProjectPeople,
} from "@entities/connected-device";
import { useIsPhoneWidth } from "@shared/lib";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { Tooltip } from "@shared/ui/Tooltip";
import { deviceText, personSummary, whereText } from "../lib/peopleText";
import { AvatarMark, PersonAvatar } from "./PersonAvatar";

const PHONE_AVATARS = 2;

export type PeopleOnlineProps = {
  people: ProjectPeople;
  /** Название документа по его идентификатору; null, если документ этому смотрящему не виден. */
  docName: (docId: string) => string | null;
  /** Перейти к документу человека. Без обработчика аватары и строки только показывают. */
  onOpenDoc?: (person: PersonOnline) => void;
};

/**
 * Люди в проекте сейчас: компактные аватары в шапке (не больше пяти и «+N»), подпись по наведению и фокусу,
 * список по нажатию на «+N» или стрелку. Пока в проекте нет никого, кроме самого смотрящего,
 * ничего не рисует: плашка Студии рядом остаётся одна.
 */
export const PeopleOnline = ({
  people,
  docName,
  onOpenDoc,
}: PeopleOnlineProps) => {
  const { t } = useTranslation("devices");
  const roleLabel = useProjectRoleLabel();
  const [open, setOpen] = useState(false);
  const isPhone = useIsPhoneWidth();
  const split = splitPeople(people.people, people.total);
  // Телефон: два аватара и «+N» одной кнопкой на 40 px, список людей в шторке.
  const shown = isPhone ? split.shown.slice(0, PHONE_AVATARS) : split.shown;
  const hidden = isPhone ? people.total - shown.length : split.hidden;
  // Одного себя показывать незачем: аватары появляются, когда в проекте есть кто-то ещё.
  if (!people.people.some((p) => !p.me)) return null;

  const parts = (person: PersonOnline) => {
    const doc = person.doc_id !== null ? docName(person.doc_id) : null;
    return {
      name: person.name,
      role: roleLabel(person.role),
      where: whereText(t, person.activity, doc),
      device: deviceText(t, person),
      doc,
    };
  };
  /** Переход к документу человека; null, если идти некуда (сам человек, нет документа, документ не виден). */
  const opener = (person: PersonOnline, doc: string | null) =>
    onOpenDoc !== undefined && !person.me && hasDocument(person) && doc !== null
      ? () => {
          onOpenDoc(person);
        }
      : null;

  const peopleList = (
    <PopoverContent width={340} aria-label={t("people.title")}>
      <div
        className="flex flex-col"
        style={{
          gap: "0.25rem",
          padding: "0.625rem",
          maxHeight: "70vh",
          overflowY: "auto",
        }}
        data-testid="people-list"
      >
        <span
          style={{
            fontSize: "0.78125rem",
            fontWeight: 600,
            padding: "0 0.125rem",
          }}
        >
          {t("people.title")}
        </span>
        <ul className="pp-list">
          {people.people.map((person) => {
            const p = parts(person);
            const go = opener(person, p.doc);
            const row = (
              <>
                <AvatarMark person={person} />
                <span className="pp-row-text">
                  <span className="pp-row-name">
                    {person.me ? t("people.you", { name: p.name }) : p.name}
                    <span className="pp-row-role">{p.role}</span>
                  </span>
                  <span className="pp-row-where">
                    {p.where}
                    {`, ${p.device}`}
                  </span>
                  {go !== null && (
                    <span className="pp-row-go">{t("people.open")}</span>
                  )}
                </span>
              </>
            );
            return (
              <li key={person.user_id} data-testid="people-row">
                {go !== null ? (
                  <button
                    type="button"
                    className="pp-row"
                    onClick={() => {
                      setOpen(false);
                      go();
                    }}
                  >
                    {row}
                  </button>
                ) : (
                  <div className="pp-row" data-static="true">
                    {row}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {people.total > people.people.length && (
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {t("people.truncated", {
              count: people.total - people.people.length,
            })}
          </span>
        )}
        <span
          className="dim"
          style={{ fontSize: "0.6875rem", lineHeight: 1.4 }}
        >
          {t("people.note")}
        </span>
      </div>
    </PopoverContent>
  );

  if (isPhone) {
    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="pp-group pp-group--phone"
            data-testid="project-people"
            data-count={people.total}
            aria-label={t("people.aria", { count: people.total })}
            aria-expanded={open}
          >
            {shown.map((person) => (
              <AvatarMark key={person.user_id} person={person} />
            ))}
            {hidden > 0 && (
              <span className="pp-more-count">{`+${String(hidden)}`}</span>
            )}
          </button>
        </PopoverTrigger>
        {peopleList}
      </Popover>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div
        className="pp-group"
        role="group"
        aria-label={t("people.aria", { count: people.total })}
        data-testid="project-people"
        data-count={people.total}
      >
        {shown.map((person) => {
          const p = parts(person);
          const summary = personSummary(t, person, p);
          const go = opener(person, p.doc);
          return (
            <Tooltip
              key={person.user_id}
              side="bottom"
              delayDuration={150}
              content={
                <span className="pp-tip">
                  <strong>
                    {person.me ? t("people.you", { name: p.name }) : p.name}
                  </strong>
                  <span>{`${p.role}, ${p.device}`}</span>
                  <span>{p.where}</span>
                  {go !== null && (
                    <span className="dim">{t("people.openHint")}</span>
                  )}
                </span>
              }
            >
              <PersonAvatar
                person={person}
                aria-label={
                  go !== null ? `${summary}. ${t("people.open")}` : summary
                }
                onClick={() => {
                  if (go !== null) go();
                  else setOpen(true);
                }}
              />
            </Tooltip>
          );
        })}
        <PopoverTrigger asChild>
          <button
            type="button"
            className="pp-more"
            data-testid="people-more"
            aria-label={t("people.list")}
            aria-expanded={open}
          >
            {hidden > 0 ? (
              <span>{t("people.more", { count: hidden })}</span>
            ) : (
              <ChevronDown size="0.75rem" aria-hidden="true" />
            )}
          </button>
        </PopoverTrigger>
      </div>
      {peopleList}
    </Popover>
  );
};
