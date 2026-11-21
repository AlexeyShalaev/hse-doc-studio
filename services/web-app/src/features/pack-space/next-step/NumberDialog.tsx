import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  PackErrorText,
  packStudioKeys,
  useRenumberPackVersion,
  type PackVersionState,
  type UpdateClass,
} from "@entities/pack-studio";
import { UPDATE_CLASSES, currentClass, isSofter } from "@features/pack-version";
import { Button, Input, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useSpaceNav } from "../context/useSpaceNav";
import { takenSuggestion } from "./submitErrors";
import { CLASS_KEYS } from "./notesDraft";

/**
 * «Изменить номер» (pack-studio-ux.md, 5.6): прежнее окно номера, только классы названы словами
 * («небольшая правка», «новые возможности», «новая редакция регламента»). Класс мягче того, что
 * требуют правки, выбрать нельзя; для новой редакции регламента можно поправить год набора.
 * После смены каталог версии переезжает, экран идёт за ним.
 */
export const NumberDialog = ({
  workspaceId,
  state,
  isOpen,
  onClose,
  beforeMove,
}: {
  workspaceId: string;
  state: PackVersionState;
  isOpen: boolean;
  onClose: () => void;
  /** Записать то, что ещё лежит в полях: каталог переезжает, несохранённое пропало бы. */
  beforeMove: () => Promise<void>;
}) => {
  const { t } = useTranslation("packSpace");
  const uid = useId();
  const nav = useSpaceNav();
  const client = useQueryClient();
  const renumber = useRenumberPackVersion(workspaceId);
  const initial = currentClass(state) ?? "patch";
  const [cls, setCls] = useState<UpdateClass>(initial);
  const [major, setMajor] = useState<string | null>(null);
  const [opened, setOpened] = useState(isOpen);
  if (isOpen !== opened) {
    setOpened(isOpen);
    if (isOpen) {
      const softer = state.minimum !== null && isSofter(initial, state.minimum);
      setCls(softer && state.minimum ? state.minimum : initial);
      setMajor(null);
      renumber.reset();
    }
  }

  const number =
    cls === "major" ? (major ?? state.numbers.major ?? "") : state.numbers[cls];
  const same = number === state.version.version;
  const suggested = takenSuggestion(renumber.error);

  const close = () => {
    if (renumber.isPending) return;
    onClose();
  };
  const submit = (version: string) => {
    void beforeMove()
      .catch(() => undefined)
      .then(() => {
        renumber.mutate(
          { ref: state.version, version },
          {
            onSuccess: (moved) => {
              // Тост здесь не нужен: он закрывал кнопку отправки. Новый номер виден в галочке
              // «Выпустить версию X» и в строке версии.
              onClose();
              void client
                .refetchQueries({ queryKey: packStudioKeys.tree(workspaceId) })
                .then(() => {
                  nav.go({
                    ref: {
                      pack: moved.version.pack,
                      template: moved.version.template,
                      version: moved.version.version,
                    },
                  });
                });
            },
          },
        );
      });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("changes.submit.number.title")}
      description={t("changes.submit.number.lead", {
        version: state.version.version,
      })}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("changes.submit.number.cancel")}
          </Button>
          <Button
            disabled={renumber.isPending || !number || same}
            onClick={() => {
              if (number) submit(number);
            }}
            data-testid="sp-number-submit"
          >
            {t("changes.submit.number.submit", { version: number ?? "" })}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.5rem" }}>
        {state.minimum && (
          <p className="sp-sb-text">
            {t("changes.submit.number.minimum", {
              minimum: t(`changes.submit.class.${CLASS_KEYS[state.minimum]}`),
            })}
          </p>
        )}
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem" }}
          role="radiogroup"
          aria-label={t("changes.submit.number.class")}
        >
          {UPDATE_CLASSES.map((value) => {
            const blocked =
              state.minimum !== null && isSofter(value, state.minimum);
            const key = CLASS_KEYS[value];
            return (
              <label
                key={value}
                className="sp-sb-choice"
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
                  data-testid={`sp-number-${key}`}
                />
                <span className="sp-sb-choice-text">
                  <span>
                    {t(`changes.submit.class.${key}`)}{" "}
                    <span className="mono">{state.numbers[value] ?? ""}</span>
                  </span>
                  <span className="sp-sb-choice-hint">
                    {blocked
                      ? t("changes.submit.number.blocked")
                      : t(`changes.submit.classHint.${key}`)}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
        {cls === "major" && (
          <Input
            label={t("changes.submit.number.majorNumber")}
            hint={t("changes.submit.number.majorHint")}
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
            text={t("changes.submit.number.unrelease")}
          />
        )}
        {renumber.isError && (
          <Notice
            tone="err"
            role="alert"
            text={<PackErrorText error={renumber.error} />}
            action={
              suggested ? (
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => {
                    submit(suggested);
                  }}
                >
                  {t("changes.submit.number.take", { version: suggested })}
                </Button>
              ) : undefined
            }
          />
        )}
      </div>
    </Modal>
  );
};
