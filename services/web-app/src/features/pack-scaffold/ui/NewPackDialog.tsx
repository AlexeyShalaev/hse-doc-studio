import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useCreatePack,
  useCreatePackTemplate,
  usePackScaffoldOptions,
  type PackScaffoldCreated,
  type ScaffoldKind,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { slugify, uniqueSlug } from "@shared/lib/slug";
import { Button, Input, Modal, Select, Spinner, TechDetails } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  defaultChoice,
  hasName,
  isPackId,
  isPackIdTaken,
  isTemplateId,
  localized,
  sourceChoices,
  type LocalizedDraft,
} from "../lib/scaffold";

/** Что создаётся: пак с первым шаблоном или шаблон в существующем паке. */
export type NewPackTarget =
  { kind: "pack" } | { kind: "template"; pack: string };

export type NewPackDialogProps = {
  workspaceId: string;
  target: NewPackTarget | null;
  onClose: () => void;
  onCreated: (created: PackScaffoldCreated) => void;
};

const EMPTY: LocalizedDraft = { ru: "", en: "" };

/**
 * «Новый пак» и «Новый шаблон» (template-studio.md, раздел 8; pack-studio-ux.md, 5.10): сначала
 * то, без чего не обойтись, названия по-русски и заготовка («Минимальный» или копия выбранной
 * версии пространства или каталога Студии), остальное под «Дополнительно»: названия по-английски,
 * короткие имена (строятся из названий сами), сопровождающий, лицензия, адрес репозитория и номер
 * первой версии. После создания открывается первая версия.
 */
export const NewPackDialog = ({
  workspaceId,
  target,
  onClose,
  onCreated,
}: NewPackDialogProps) => {
  const { t } = useTranslation("packStudio");
  const uid = useId();
  const open = target !== null;
  const forPack = target?.kind === "pack";
  const options = usePackScaffoldOptions(workspaceId, open);
  const createPack = useCreatePack(workspaceId);
  const createTemplate = useCreatePackTemplate(workspaceId);
  const mutation = forPack ? createPack : createTemplate;

  const [packIdTyped, setPackIdTyped] = useState<string | null>(null);
  const [packName, setPackName] = useState<LocalizedDraft>(EMPTY);
  const [maintainer, setMaintainer] = useState<{
    name: string;
    email: string;
  } | null>(null);
  const [license, setLicense] = useState<string | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [templateIdTyped, setTemplateIdTyped] = useState<string | null>(null);
  const [templateName, setTemplateName] = useState<LocalizedDraft>(EMPTY);
  const [kind, setKind] = useState<ScaffoldKind>("minimal");
  const [sourceKey, setSourceKey] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);

  const data = options.data;
  const choices = useMemo(() => sourceChoices(data), [data]);
  const chosen =
    choices.find((choice) => choice.key === sourceKey) ??
    defaultChoice(choices);
  const owner = maintainer ?? {
    name: data?.maintainer?.name ?? "",
    email: data?.maintainer?.email ?? "",
  };
  const chosenLicense = license ?? data?.license ?? "Apache-2.0";
  const chosenVersion = version ?? data?.version ?? "";
  // Короткие имена (папки на диске) строятся из названий; свои вводятся под «Дополнительно».
  const packId =
    packIdTyped ??
    uniqueSlug(
      slugify(packName.ru.trim() || packName.en.trim(), "-"),
      data?.taken_packs ?? [],
      "-",
    );
  const templateId =
    templateIdTyped ??
    slugify(templateName.ru.trim() || templateName.en.trim(), "_");

  const packIdError =
    !forPack || packId === ""
      ? undefined
      : !isPackId(packId)
        ? t("scaffold.idInvalid")
        : isPackIdTaken(data, packId)
          ? t("scaffold.packIdTaken")
          : undefined;
  const templateIdError =
    templateId !== "" && !isTemplateId(templateId)
      ? t("scaffold.idInvalid")
      : undefined;
  // Названия есть, а короткого имени из них не вышло (например, только иероглифы): покажем поле.
  const idMissing =
    (hasName(templateName) && templateId === "") ||
    (forPack && hasName(packName) && packId === "") ||
    templateIdError !== undefined ||
    packIdError !== undefined;
  const ready =
    data !== undefined &&
    isTemplateId(templateId) &&
    hasName(templateName) &&
    chosenVersion !== "" &&
    (kind === "minimal" || chosen !== undefined) &&
    (!forPack || (isPackId(packId) && !packIdError && hasName(packName)));

  const reset = () => {
    createPack.reset();
    createTemplate.reset();
    setPackIdTyped(null);
    setPackName(EMPTY);
    setMaintainer(null);
    setLicense(null);
    setSourceUrl("");
    setTemplateIdTyped(null);
    setTemplateName(EMPTY);
    setKind("minimal");
    setSourceKey(null);
    setVersion(null);
  };

  const close = () => {
    if (mutation.isPending) return;
    reset();
    onClose();
  };

  const scaffold =
    kind === "copy" && chosen
      ? { kind, source: chosen.source }
      : { kind: "minimal" as const };

  const done = (created: PackScaffoldCreated) => {
    toast.success(
      forPack
        ? t("scaffold.donePack", {
            pack:
              packName.ru.trim() || packName.en.trim() || created.version.pack,
          })
        : t("scaffold.doneTemplate", {
            template:
              templateName.ru.trim() ||
              templateName.en.trim() ||
              created.version.template,
          }),
    );
    reset();
    onCreated(created);
  };

  const submit = () => {
    if (!target || !ready) return;
    const template = { id: templateId, name: localized(templateName) };
    if (target.kind === "pack") {
      createPack.mutate(
        {
          id: packId,
          name: localized(packName),
          maintainer: owner.name.trim()
            ? { name: owner.name.trim(), email: owner.email.trim() }
            : null,
          license: chosenLicense.trim() || null,
          source: sourceUrl.trim() || null,
          template,
          scaffold,
          version: chosenVersion,
        },
        { onSuccess: done },
      );
      return;
    }
    createTemplate.mutate(
      {
        pack: target.pack,
        body: { ...template, scaffold, version: chosenVersion },
      },
      { onSuccess: done },
    );
  };

  const radio = (value: ScaffoldKind) => (
    <label key={value} className="ps-choice" htmlFor={`${uid}-${value}`}>
      <input
        id={`${uid}-${value}`}
        type="radio"
        name={`${uid}-kind`}
        checked={kind === value}
        onChange={() => {
          setKind(value);
        }}
        style={{ accentColor: "var(--accent)" }}
        data-testid={`scaffold-kind-${value}`}
      />
      <span className="ps-choice-text">
        <span>{t(`scaffold.${value}`)}</span>
        <span className="ps-choice-hint">{t(`scaffold.${value}Hint`)}</span>
      </span>
    </label>
  );

  return (
    <Modal
      isOpen={open}
      onClose={close}
      title={t(forPack ? "scaffold.packTitle" : "scaffold.templateTitle")}
      description={
        target?.kind === "template"
          ? t("scaffold.templateLead", { pack: target.pack })
          : t("scaffold.packLead")
      }
      width={600}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={mutation.isPending || !ready}
            onClick={submit}
            data-testid="scaffold-submit"
          >
            {mutation.isPending ? <Spinner size="sm" /> : null}
            {t(forPack ? "scaffold.submitPack" : "scaffold.submitTemplate")}
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
          <section className="ps-scaffold-section">
            {forPack && (
              <Input
                label={t("scaffold.packName")}
                hint={t("scaffold.packNameHint")}
                value={packName.ru}
                onChange={(e) => {
                  setPackName({ ...packName, ru: e.target.value });
                }}
                autoFocus
                data-testid="scaffold-pack-name-ru"
              />
            )}
            <Input
              label={t("scaffold.templateName")}
              hint={t("scaffold.templateNameHint")}
              value={templateName.ru}
              onChange={(e) => {
                setTemplateName({ ...templateName, ru: e.target.value });
              }}
              autoFocus={!forPack}
              data-testid="scaffold-template-name-ru"
            />
          </section>
          <section className="ps-scaffold-section">
            <h3 className="ps-scaffold-title">{t("scaffold.start")}</h3>
            <div
              className="flex flex-col"
              style={{ gap: "0.375rem" }}
              role="radiogroup"
              aria-label={t("scaffold.start")}
            >
              {radio("minimal")}
              {radio("copy")}
            </div>
            {kind === "copy" &&
              (choices.length === 0 ? (
                <Notice
                  tone="warn"
                  role="status"
                  text={t("scaffold.noSources")}
                />
              ) : (
                <div className="field">
                  <label htmlFor={`${uid}-source`}>
                    {t("scaffold.copyFrom")}
                  </label>
                  <Select
                    id={`${uid}-source`}
                    value={chosen?.key ?? ""}
                    onValueChange={setSourceKey}
                    ariaLabel={t("scaffold.copyFrom")}
                    options={choices.map((choice) => ({
                      value: choice.key,
                      label: `${choice.title} ${choice.source.version} · ${t(
                        choice.source.origin === "workspace"
                          ? "scaffold.originWorkspace"
                          : "scaffold.originCatalog",
                      )}`,
                    }))}
                  />
                </div>
              ))}
          </section>
          <TechDetails
            title={t("scaffold.more")}
            open={idMissing ? true : undefined}
            testId="scaffold-more"
          >
            {forPack && (
              <section className="ps-scaffold-section">
                <h3 className="ps-scaffold-title">
                  {t("scaffold.packSection")}
                </h3>
                <Input
                  label={t("scaffold.nameEn")}
                  hint={t("scaffold.nameHint")}
                  value={packName.en}
                  onChange={(e) => {
                    setPackName({ ...packName, en: e.target.value });
                  }}
                  data-testid="scaffold-pack-name-en"
                />
                <Input
                  label={t("scaffold.packId")}
                  hint={t("scaffold.packIdHint")}
                  {...(packIdError ? { error: packIdError } : {})}
                  value={packId}
                  onChange={(e) => {
                    setPackIdTyped(e.target.value.trim());
                  }}
                  isMono
                  data-testid="scaffold-pack-id"
                />
                <div className="ps-scaffold-pair">
                  <Input
                    label={t("scaffold.maintainerName")}
                    value={owner.name}
                    onChange={(e) => {
                      setMaintainer({ ...owner, name: e.target.value });
                    }}
                  />
                  <Input
                    label={t("scaffold.maintainerEmail")}
                    type="email"
                    value={owner.email}
                    onChange={(e) => {
                      setMaintainer({ ...owner, email: e.target.value });
                    }}
                  />
                </div>
                <div className="ps-scaffold-pair">
                  <Input
                    label={t("scaffold.license")}
                    hint={t("scaffold.licenseHint")}
                    value={chosenLicense}
                    onChange={(e) => {
                      setLicense(e.target.value);
                    }}
                    isMono
                  />
                  <Input
                    label={t("scaffold.sourceUrl")}
                    hint={t("scaffold.sourceUrlHint")}
                    value={sourceUrl}
                    onChange={(e) => {
                      setSourceUrl(e.target.value);
                    }}
                    placeholder="https://"
                    isMono
                  />
                </div>
              </section>
            )}
            <section className="ps-scaffold-section">
              {forPack && (
                <h3 className="ps-scaffold-title">
                  {t("scaffold.templateSection")}
                </h3>
              )}
              <Input
                label={t("scaffold.nameEn")}
                hint={t("scaffold.nameHint")}
                value={templateName.en}
                onChange={(e) => {
                  setTemplateName({ ...templateName, en: e.target.value });
                }}
                data-testid="scaffold-template-name-en"
              />
              <div className="ps-scaffold-pair">
                <Input
                  label={t("scaffold.templateId")}
                  hint={t("scaffold.templateIdHint")}
                  {...(templateIdError ? { error: templateIdError } : {})}
                  value={templateId}
                  onChange={(e) => {
                    setTemplateIdTyped(e.target.value.trim());
                  }}
                  isMono
                  data-testid="scaffold-template-id"
                />
                <Input
                  label={t("scaffold.version")}
                  hint={t("scaffold.versionHint")}
                  value={chosenVersion}
                  onChange={(e) => {
                    setVersion(e.target.value.trim());
                  }}
                  isMono
                  data-testid="scaffold-version"
                />
              </div>
            </section>
          </TechDetails>
          {mutation.isError && (
            <Notice
              tone="err"
              role="alert"
              text={packErrorText(mutation.error)}
            />
          )}
        </div>
      )}
    </Modal>
  );
};
