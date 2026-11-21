import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { slugify, uniqueSlug } from "@shared/lib/slug";
import { Button, Modal, TechDetails } from "@shared/ui";
import { fieldKeyProblem } from "../lib/fields";
import { ITEM_ID } from "../lib/raw";
import { useModelEditor } from "../model/modelEditor";
import { FormRow } from "./kit";

/**
 * Новый элемент (документ, анкета, секция, поле, группа, вариант): сначала название, остальное под
 * «Дополнительно». Короткое имя латиницей (папка документа, ключ поля) строится из названия само и
 * правится вручную; название по-английски необязательно.
 */
export const NewItemDialog = ({
  isOpen,
  title,
  idLabel,
  idHint,
  taken,
  pattern = "key",
  extra,
  onClose,
  onCreate,
}: {
  isOpen: boolean;
  title: string;
  /** Подпись короткого имени (оно лежит под «Дополнительно»). */
  idLabel: string;
  idHint?: string | undefined;
  taken: string[];
  pattern?: "key" | "id";
  extra?: ReactNode | undefined;
  onClose: () => void;
  onCreate: (id: string, label: Record<string, string>) => Promise<void>;
}) => {
  const { t } = useTranslation("packForms");
  const { busy } = useModelEditor();
  // Своё короткое имя: пока человек его не трогал, имя следует за названием.
  const [typed, setTyped] = useState<string | null>(null);
  const [label, setLabel] = useState<Record<string, string>>({});
  const named = label.ru?.trim() || label.en?.trim() || "";
  const generated = (() => {
    const base = slugify(named, "_");
    const safe = pattern === "key" && /^[0-9]/.test(base) ? `f_${base}` : base;
    return uniqueSlug(safe, taken, "_");
  })();
  const trimmed = (typed ?? generated).trim();
  const problem =
    pattern === "key"
      ? fieldKeyProblem(trimmed, taken)
      : !ITEM_ID.test(trimmed)
        ? "format"
        : taken.includes(trimmed)
          ? "taken"
          : null;
  const reset = () => {
    setTyped(null);
    setLabel({});
  };
  const close = () => {
    reset();
    onClose();
  };
  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={title}
      width={480}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("cancel")}
          </Button>
          <Button
            disabled={busy || problem !== null || !label.ru?.trim()}
            data-testid="pf-new-submit"
            onClick={() => {
              void onCreate(trimmed, label).then(reset);
            }}
          >
            {t("kit.create")}
          </Button>
        </>
      }
    >
      <div className="pf-dialog">
        <FormRow label={t("kit.labelIn.ru")}>
          {(inputId) => (
            <input
              id={inputId}
              className="input"
              value={label.ru ?? ""}
              autoFocus
              data-testid="pf-new-label-ru"
              onChange={(e) => {
                setLabel({ ...label, ru: e.target.value });
              }}
            />
          )}
        </FormRow>
        {extra}
        <TechDetails title={t("kit.more")} testId="pf-new-more">
          <FormRow label={t("kit.labelIn.en")}>
            {(inputId) => (
              <input
                id={inputId}
                className="input"
                value={label.en ?? ""}
                data-testid="pf-new-label-en"
                onChange={(e) => {
                  setLabel({ ...label, en: e.target.value });
                }}
              />
            )}
          </FormRow>
          <FormRow
            label={idLabel}
            hint={
              trimmed && problem ? (
                <span className="pf-error-text">
                  {t(`kit.idProblem.${problem}`)}
                </span>
              ) : (
                (idHint ?? t(`kit.tech.idHint.${pattern}`))
              )
            }
          >
            {(inputId) => (
              <input
                id={inputId}
                className="input mono"
                value={typed ?? generated}
                data-testid="pf-new-id"
                onChange={(e) => {
                  setTyped(e.target.value);
                }}
              />
            )}
          </FormRow>
        </TechDetails>
      </div>
    </Modal>
  );
};
