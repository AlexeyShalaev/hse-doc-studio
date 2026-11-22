import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWritePackScenario } from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Input, Modal } from "@shared/ui";
import {
  classifyFailure,
  formOf,
  freeId,
  requestOf,
  scenarioName,
  slugify,
  type ScenarioFailure,
} from "@entities/pack-studio/outcome/scenarios";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { EXAMPLE_PARAM } from "./useSituationDelta";
import type { SituationModel } from "./useSituationModel";

/**
 * «Запомнить этот случай»: одно поле, название. Условия берутся с экрана (выбранный случай и
 * изменения поверх него). Под «Дополнительно» запоминание результата, чтобы заметить, когда он
 * изменится (прежний «снимок»); утверждения и версии настраиваются в «Содержимом».
 */
export const SaveCaseDialog = ({
  model,
  onClose,
}: {
  model: SituationModel;
  onClose: () => void;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const { workspace, versionRef, location } = useSpace();
  const situation = useSituation();
  const write = useWritePackScenario(
    workspace.id,
    versionRef.pack,
    versionRef.template,
  );
  const [name, setName] = useState("");
  const [remember, setRemember] = useState(true);
  const [failure, setFailure] = useState<ScenarioFailure | null>(null);
  const [touched, setTouched] = useState(false);

  const picked = model.cases.find((entry) => entry.id === situation.caseId);
  const inputs = { ...(picked?.scenario?.inputs ?? {}), ...situation.inputs };
  const count = Object.keys(inputs).length;
  const example = new URLSearchParams(location.search).get(EXAMPLE_PARAM);
  const empty = name.trim() === "";

  const submit = async () => {
    setTouched(true);
    if (empty) return;
    const taken = new Set(model.cases.map((entry) => entry.id));
    const id = freeId(slugify(name.trim()), taken);
    const form = formOf(null, versionRef.version, id);
    form.name[i18n.language.startsWith("en") ? "en" : "ru"] = name.trim();
    form.snapshot = remember;
    form.recordSnapshot = remember;
    try {
      const entry = await write.mutateAsync({
        scenario: id,
        ifMatch: null,
        body: requestOf(form, {
          base: null,
          inputs,
          example: picked?.scenario?.example ?? example,
          version: versionRef.version,
          state: "work_tree",
        }),
      });
      toast.success(
        t("situation.save.saved", { name: scenarioName(entry, i18n.language) }),
      );
      // Условия теперь в файле: на полосе остаётся выбранный случай без изменений поверх.
      situation.setInputs({}, entry.id);
      onClose();
    } catch (error) {
      setFailure(classifyFailure(error));
    }
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={480}
      title={t("situation.save.title")}
      description={t("situation.save.lead")}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            {t("situation.save.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={write.isPending}
            data-testid="sp-sit-save-submit"
            onClick={() => void submit()}
          >
            {write.isPending
              ? t("situation.save.saving")
              : t("situation.save.submit")}
          </button>
        </>
      }
    >
      <div className="sp-sit-dialog" data-testid="sp-sit-save">
        <Input
          label={t("situation.save.name")}
          value={name}
          maxLength={200}
          autoFocus
          placeholder={t("situation.save.namePlaceholder")}
          hint={t("situation.save.count", { count })}
          {...(touched && empty
            ? { error: t("situation.save.nameRequired") }
            : {})}
          data-testid="sp-sit-save-name"
          onChange={(event) => {
            setName(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
        />
        <details className="sp-sit-more-opts">
          <summary>{t("situation.save.advanced")}</summary>
          <label className="sp-sit-check">
            <input
              type="checkbox"
              checked={remember}
              data-testid="sp-sit-save-remember"
              onChange={(event) => {
                setRemember(event.target.checked);
              }}
            />
            <span>
              {t("situation.save.remember")}
              <span className="sp-sit-pop-note">
                {t("situation.save.rememberHint")}
              </span>
            </span>
          </label>
        </details>
        {failure ? (
          <p className="sp-sit-error" role="alert">
            {failure.kind === "taken"
              ? t("situation.save.taken")
              : failure.kind === "invalid"
                ? t("situation.save.invalid", { reason: failure.reason })
                : t("situation.save.failed")}
          </p>
        ) : null}
      </div>
    </Modal>
  );
};
