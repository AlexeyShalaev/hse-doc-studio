import { useId, type ReactNode } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAddInput } from "../../lib/useAddInput";
import type { OutcomeSelection } from "../../lib/urlState";
import { PickItem } from "./parts";
import "../../pale.css";

type AddInputActionProps = {
  /** Элемент, который «Добавить во вводных» возвращает в результат. */
  el: OutcomeSelection & {
    section: Exclude<OutcomeSelection["section"], "branches">;
  };
  /** Название элемента для скринридера: «Добавить во вводных: Консультант». */
  name: string;
};

/**
 * Действие бледного слота «Добавить во вводных»: применяет ОДНУ вводную, которую предлагает
 * сервер («что если» элемента), через адрес экрана. Нечего предложить: слот пишет это словами.
 */
export const AddInputAction = ({ el, name }: AddInputActionProps) => {
  const { t } = useTranslation("packOutcome");
  const add = useAddInput(el);
  const noteId = useId();
  const note = add.searching
    ? t("pale.searching")
    : add.failed
      ? t("pale.failed")
      : add.none
        ? t("pale.none")
        : "";
  return (
    <span className="po-pale-action">
      <button
        type="button"
        className="btn sm"
        data-po-pick="true"
        aria-label={t("pale.addLabel", { name })}
        aria-describedby={note === "" ? undefined : noteId}
        aria-busy={add.searching || undefined}
        disabled={add.searching}
        data-testid={`outcome-pale-add-${el.section}-${el.id}`}
        onClick={add.run}
      >
        <Plus size="0.8125rem" aria-hidden="true" />
        {t("pale.add")}
      </button>
      <span
        id={noteId}
        className="po-note"
        role="status"
        data-testid={`outcome-pale-note-${el.section}-${el.id}`}
      >
        {note}
      </span>
    </span>
  );
};

type PaleSlotProps = {
  el: AddInputActionProps["el"];
  /** Название для заголовка и для скринридера. */
  name: string;
  badges?: ReactNode;
  /** «Почему нет» одной строкой. */
  children: ReactNode;
  testId: string;
};

/**
 * Бледный слот: элемент, которого нет при этой комбинации, но который есть в версии. Стоит на
 * своём месте приглушённым, с кратким «почему нет» и действием «Добавить во вводных». Один
 * компонент на секции «Документы», «Участники» и «Маршрут» (карточки), пункты точек сдачи берут
 * то же действие `AddInputAction`.
 */
export const PaleSlot = ({
  el,
  name,
  badges,
  children,
  testId,
}: PaleSlotProps) => (
  <PickItem
    el={el}
    muted
    pale
    testId={testId}
    title={name}
    badges={badges}
    action={<AddInputAction el={el} name={name} />}
  >
    {children}
  </PickItem>
);
