import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, Modal } from "@shared/ui";
import { fieldKeyProblem } from "../lib/fields";
import { ITEM_ID } from "../lib/raw";
import { useModelEditor } from "../model/modelEditor";
import { FormRow } from "./kit";

/** Новый элемент: id (ключ поля или id документа, анкеты, секции) и подпись ru и en. */
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
  const [id, setId] = useState("");
  const [label, setLabel] = useState<Record<string, string>>({});
  const trimmed = id.trim();
  const problem =
    pattern === "key"
      ? fieldKeyProblem(trimmed, taken)
      : !ITEM_ID.test(trimmed)
        ? "format"
        : taken.includes(trimmed)
          ? "taken"
          : null;
  const close = () => {
    setId("");
    setLabel({});
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
              void onCreate(trimmed, label).then(() => {
                setId("");
                setLabel({});
              });
            }}
          >
            {t("kit.create")}
          </Button>
        </>
      }
    >
      <div className="pf-dialog">
        <FormRow
          label={idLabel}
          hint={
            trimmed && problem ? (
              <span className="pf-error-text">
                {t(`kit.idProblem.${problem}`)}
              </span>
            ) : (
              (idHint ?? t(`kit.idHint.${pattern}`))
            )
          }
        >
          {(inputId) => (
            <input
              id={inputId}
              className="input mono"
              value={id}
              autoFocus
              data-testid="pf-new-id"
              onChange={(e) => {
                setId(e.target.value);
              }}
            />
          )}
        </FormRow>
        {(["ru", "en"] as const).map((lang) => (
          <FormRow key={lang} label={t(`kit.labelIn.${lang}`)}>
            {(inputId) => (
              <input
                id={inputId}
                className="input"
                value={label[lang] ?? ""}
                data-testid={`pf-new-label-${lang}`}
                onChange={(e) => {
                  setLabel({ ...label, [lang]: e.target.value });
                }}
              />
            )}
          </FormRow>
        ))}
        {extra}
      </div>
    </Modal>
  );
};
