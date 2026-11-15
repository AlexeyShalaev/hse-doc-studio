import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useRenumberPackVersion,
  type PackVersionMoved,
  type PackVersionState,
  type UpdateClass,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Input, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { UPDATE_CLASSES, currentClass, isSofter } from "../lib/versionWizard";

export type RenumberDialogProps = {
  workspaceId: string;
  state: PackVersionState;
  isOpen: boolean;
  onClose: () => void;
  onMoved: (moved: PackVersionMoved) => void;
};

/**
 * Номер черновика по классу (template-studio.md, 7.1, шаг 3): класс мягче
 * минимума по жёстким правилам выбрать нельзя, строже можно. Major спрашивает
 * год набора: номер можно поправить руками.
 */
export const RenumberDialog = ({
  workspaceId,
  state,
  isOpen,
  onClose,
  onMoved,
}: RenumberDialogProps) => {
  const { t } = useTranslation("packStudio");
  const uid = useId();
  const renumber = useRenumberPackVersion(workspaceId);
  const initial = currentClass(state) ?? "patch";
  const [cls, setCls] = useState<UpdateClass>(initial);
  const [major, setMajor] = useState<string | null>(null);
  const [opened, setOpened] = useState(isOpen);
  if (isOpen !== opened) {
    setOpened(isOpen);
    if (isOpen) {
      const softer = state.minimum && isSofter(initial, state.minimum);
      setCls(softer && state.minimum ? state.minimum : initial);
      setMajor(null);
    }
  }

  const number =
    cls === "major" ? (major ?? state.numbers.major ?? "") : state.numbers[cls];
  const same = number === state.version.version;
  const suggested =
    renumber.error instanceof ApiError &&
    renumber.error.code === "version_taken"
      ? renumber.error.data?.suggested
      : undefined;

  const close = () => {
    if (renumber.isPending) return;
    renumber.reset();
    onClose();
  };

  const submit = (version: string) => {
    renumber.mutate(
      { ref: state.version, version },
      {
        onSuccess: (moved) => {
          toast.success(
            t("version.renumber.done", { version: moved.version.version }),
          );
          renumber.reset();
          onMoved(moved);
        },
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("version.renumber.title")}
      description={t("version.renumber.lead", {
        version: state.version.version,
      })}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={renumber.isPending || !number || same}
            onClick={() => {
              if (number) submit(number);
            }}
            data-testid="version-renumber-submit"
          >
            {t("version.renumber.submit", { version: number ?? "" })}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.5rem" }}>
        {state.minimum && (
          <p className="ps-dialog-text">
            {t("version.renumber.minimum", {
              minimum: t(`version.class.${state.minimum}`),
            })}
          </p>
        )}
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem" }}
          role="radiogroup"
          aria-label={t("version.create.class")}
        >
          {UPDATE_CLASSES.map((value) => {
            const blocked =
              state.minimum !== null && isSofter(value, state.minimum);
            return (
              <label
                key={value}
                className="ps-choice"
                htmlFor={`${uid}-${value}`}
                data-disabled={blocked ? "true" : "false"}
              >
                <input
                  id={`${uid}-${value}`}
                  type="radio"
                  name={`${uid}-class`}
                  checked={cls === value}
                  disabled={blocked}
                  onChange={() => {
                    setCls(value);
                  }}
                  style={{ accentColor: "var(--accent)" }}
                  data-testid={`version-renumber-${value}`}
                />
                <span className="ps-choice-text">
                  <span>
                    {t(`version.class.${value}`)}{" "}
                    <span className="mono">{state.numbers[value] ?? ""}</span>
                  </span>
                  <span className="ps-choice-hint">
                    {blocked
                      ? t("version.renumber.blocked")
                      : t(`version.classHint.${value}`)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        {cls === "major" && (
          <Input
            label={t("version.create.majorNumber")}
            hint={t("version.create.majorHint")}
            value={number ?? ""}
            onChange={(e) => {
              setMajor(e.target.value.trim());
            }}
            isMono
          />
        )}
        {state.registered && (
          <Notice
            tone="info"
            role="status"
            text={t("version.renumber.unrelease")}
          />
        )}
        {renumber.isError && (
          <Notice
            tone="err"
            role="alert"
            text={packErrorText(renumber.error)}
            action={
              typeof suggested === "string" ? (
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => {
                    submit(suggested);
                  }}
                >
                  {t("version.create.takeSuggested", { version: suggested })}
                </Button>
              ) : undefined
            }
          />
        )}
      </div>
    </Modal>
  );
};
