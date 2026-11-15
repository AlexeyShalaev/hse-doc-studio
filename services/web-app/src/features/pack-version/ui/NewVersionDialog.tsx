import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useCreatePackVersion,
  usePackVersionOptions,
  type PackVersionCreated,
  type UpdateClass,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Input, Modal, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { UPDATE_CLASSES } from "../lib/versionWizard";

export type NewVersionTarget = {
  pack: string;
  template: string;
  /** База копии; без неё последняя выпущенная. */
  base?: string | undefined;
};

export type NewVersionDialogProps = {
  workspaceId: string;
  target: NewVersionTarget | null;
  onClose: () => void;
  onCreated: (created: PackVersionCreated) => void;
};

/**
 * Шаг 1 мастера «Новая версия» (template-studio.md, 7.1): база по умолчанию
 * последняя выпущенная, класс даёт номер (patch, minor, major с годом набора),
 * каталог базы копируется в черновик `beta` с пустыми заметками.
 */
export const NewVersionDialog = ({
  workspaceId,
  target,
  onClose,
  onCreated,
}: NewVersionDialogProps) => {
  const { t } = useTranslation("packStudio");
  const uid = useId();
  const options = usePackVersionOptions(
    workspaceId,
    target?.pack ?? "",
    target?.template ?? "",
    target !== null,
  );
  const create = useCreatePackVersion(workspaceId);
  const [base, setBase] = useState<string | null>(null);
  const [cls, setCls] = useState<UpdateClass>("patch");
  const [major, setMajor] = useState<string | null>(null);

  const close = () => {
    if (create.isPending) return;
    create.reset();
    setBase(null);
    setCls("patch");
    setMajor(null);
    onClose();
  };

  const data = options.data;
  const chosenBase = base ?? target?.base ?? data?.default_base ?? "";
  const number =
    cls === "major" ? (major ?? data?.numbers.major ?? "") : data?.numbers[cls];
  const taken =
    create.error instanceof ApiError && create.error.code === "version_taken"
      ? create.error.data?.suggested
      : undefined;

  const submit = (version?: string) => {
    if (!target) return;
    create.mutate(
      {
        pack: target.pack,
        template: target.template,
        body: {
          base: chosenBase || null,
          ...(version || cls === "major"
            ? { version: version ?? number ?? null }
            : { update_class: cls }),
        },
      },
      {
        onSuccess: (created) => {
          toast.success(
            t("version.create.done", { version: created.version.version }),
          );
          create.reset();
          setBase(null);
          setMajor(null);
          onCreated(created);
        },
      },
    );
  };

  const radio = (value: UpdateClass) => (
    <label key={value} className="ps-choice" htmlFor={`${uid}-${value}`}>
      <input
        id={`${uid}-${value}`}
        type="radio"
        name={`${uid}-class`}
        checked={cls === value}
        onChange={() => {
          setCls(value);
        }}
        style={{ accentColor: "var(--accent)" }}
        data-testid={`new-version-class-${value}`}
      />
      <span className="ps-choice-text">
        <span>
          {t(`version.class.${value}`)}{" "}
          <span className="mono">{data?.numbers[value] ?? ""}</span>
        </span>
        <span className="ps-choice-hint">
          {t(`version.classHint.${value}`)}
        </span>
      </span>
    </label>
  );

  return (
    <Modal
      isOpen={target !== null}
      onClose={close}
      title={t("version.create.title")}
      description={
        target
          ? t("version.create.lead", {
              pack: target.pack,
              template: target.template,
            })
          : undefined
      }
      width={560}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={create.isPending || !data || !chosenBase || !number}
            onClick={() => {
              submit();
            }}
            data-testid="new-version-submit"
          >
            {create.isPending ? <Spinner size="sm" /> : null}
            {t("version.create.submit", { version: number ?? "" })}
          </Button>
        </>
      }
    >
      {options.isPending ? (
        <div className="flex justify-center" style={{ padding: "1rem" }}>
          <Spinner size="md" />
        </div>
      ) : options.isError ? (
        <Notice tone="err" role="alert" text={packErrorText(options.error)} />
      ) : (
        <div className="flex flex-col" style={{ gap: "0.75rem" }}>
          <div className="field">
            <label htmlFor={`${uid}-base`}>{t("version.create.base")}</label>
            <Select
              id={`${uid}-base`}
              value={chosenBase}
              onValueChange={setBase}
              ariaLabel={t("version.create.base")}
              options={options.data.versions.map((v) => ({
                value: v.version,
                label: `${v.version} · ${
                  v.released
                    ? t("version.base.released")
                    : v.registered
                      ? t("version.base.registered")
                      : (v.status ?? t("version.base.draft"))
                }`,
              }))}
            />
            <p className="hint">{t("version.create.baseHint")}</p>
          </div>
          <div
            className="flex flex-col"
            style={{ gap: "0.375rem" }}
            role="radiogroup"
            aria-label={t("version.create.class")}
          >
            {UPDATE_CLASSES.map(radio)}
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
              data-testid="new-version-major"
            />
          )}
          <p className="ps-dialog-text">{t("version.create.copyHint")}</p>
          {create.isError && (
            <Notice
              tone="err"
              role="alert"
              text={packErrorText(create.error)}
              action={
                typeof taken === "string" ? (
                  <Button
                    size="xs"
                    variant="secondary"
                    onClick={() => {
                      submit(taken);
                    }}
                  >
                    {t("version.create.takeSuggested", { version: taken })}
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>
      )}
    </Modal>
  );
};
