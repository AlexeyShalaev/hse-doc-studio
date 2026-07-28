import { Briefcase, Building, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { HsePersonLookupButton } from "@entities/hse-person";
import { SectionCard } from "../SectionCard";
import type { Person } from "./types";

type SupervisorRowProps = {
  value: Person;
  primary?: boolean;
  // Override the card heading (e.g. академический руководитель ОП).
  label?: string;
  // The programme's academic supervisor is always from the university and has
  // no printed degree line — hide the controls that don't apply.
  hideRole?: boolean;
  hideDegree?: boolean;
  onChange: (patch: Partial<Person>) => void;
  onRemove?: () => void;
};

const SupervisorRow = ({
  value,
  primary,
  label,
  hideRole,
  hideDegree,
  onChange,
  onRemove,
}: SupervisorRowProps) => {
  const { t } = useTranslation("workspace");
  return (
    <div className="card" style={{ padding: 14, background: "var(--bg-2)" }}>
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: 10 }}
      >
        <div className="flex items-center gap-2">
          {value.role === "university" ? (
            <Building size={13} style={{ color: "var(--accent)" }} />
          ) : (
            <Briefcase size={13} style={{ color: "var(--c-warn)" }} />
          )}
          <strong style={{ fontSize: 12.5 }}>
            {label ??
              (primary
                ? t("projectSettings.primarySupervisor")
                : t("projectSettings.coSupervisor"))}
          </strong>
        </div>
        <div className="flex items-center gap-2">
          {!hideRole && (
            <div className="seg">
              <button
                type="button"
                className={clsx(value.role === "university" && "active")}
                onClick={() => {
                  onChange({ role: "university" });
                }}
              >
                <Building size={10} />
                {t("projectSettings.university")}
              </button>
              <button
                type="button"
                className={clsx(value.role === "company" && "active")}
                onClick={() => {
                  onChange({ role: "company" });
                }}
              >
                <Briefcase size={10} />
                {t("projectSettings.company")}
              </button>
            </div>
          )}
          {onRemove && (
            <button
              type="button"
              className="icon-btn sm"
              style={{ color: "var(--c-err)" }}
              onClick={onRemove}
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      </div>
      <div className="flex justify-end" style={{ marginBottom: 8 }}>
        <HsePersonLookupButton
          initialQuery={value.name}
          onSelect={(fields) => {
            onChange({
              role: "university",
              name: fields.name,
              title: fields.title,
              ...(hideDegree ? {} : { degree: fields.degree }),
            });
          }}
        />
      </div>
      <div className="flex gap-3">
        <div className="field flex-1">
          <label>{t("projectSettings.fullName")}</label>
          <input
            className="input"
            value={value.name}
            onChange={(e) => {
              onChange({ name: e.target.value });
            }}
          />
        </div>
        <div className="field flex-1">
          <label>{t("projectSettings.position")}</label>
          <input
            className="input"
            value={value.title ?? ""}
            onChange={(e) => {
              onChange({ title: e.target.value });
            }}
          />
        </div>
        {!hideDegree && (
          <div className="field flex-1">
            <label>{t("projectSettings.degree")}</label>
            <input
              className="input"
              value={value.degree ?? ""}
              placeholder={t("projectSettings.degreePlaceholder")}
              onChange={(e) => {
                onChange({ degree: e.target.value });
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export type SupervisorSectionProps = {
  supervisor: Person | null;
  coSupervisor: Person | null;
  academicSupervisor: Person | null;
  onChangeSupervisor: (patch: Partial<Person>) => void;
  onAddSupervisor: () => void;
  onRemoveSupervisor: () => void;
  onChangeCoSupervisor: (patch: Partial<Person>) => void;
  onAddCoSupervisor: () => void;
  onRemoveCoSupervisor: () => void;
  onChangeAcademicSupervisor: (patch: Partial<Person>) => void;
  onAddAcademicSupervisor: () => void;
  onRemoveAcademicSupervisor: () => void;
};

export const SupervisorSection = ({
  supervisor,
  coSupervisor,
  academicSupervisor,
  onChangeSupervisor,
  onAddSupervisor,
  onRemoveSupervisor,
  onChangeCoSupervisor,
  onAddCoSupervisor,
  onRemoveCoSupervisor,
  onChangeAcademicSupervisor,
  onAddAcademicSupervisor,
  onRemoveAcademicSupervisor,
}: SupervisorSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionSupervisor")} fullSpan>
      <div className="flex flex-col" style={{ gap: 10 }}>
        {supervisor ? (
          <SupervisorRow
            value={supervisor}
            primary
            onChange={onChangeSupervisor}
            onRemove={onRemoveSupervisor}
          />
        ) : (
          <button
            type="button"
            className="btn ghost self-start"
            onClick={onAddSupervisor}
          >
            <Plus size={11} />
            {t("projectSettings.addSupervisor")}
          </button>
        )}
        {coSupervisor ? (
          <SupervisorRow
            value={coSupervisor}
            onChange={onChangeCoSupervisor}
            onRemove={onRemoveCoSupervisor}
          />
        ) : (
          <button
            type="button"
            className="btn ghost self-start"
            onClick={onAddCoSupervisor}
          >
            <Plus size={11} />
            {t("projectSettings.addCoSupervisor")}
          </button>
        )}
        {academicSupervisor ? (
          <SupervisorRow
            value={academicSupervisor}
            label={t("projectSettings.academicSupervisor")}
            hideRole
            hideDegree
            onChange={onChangeAcademicSupervisor}
            onRemove={onRemoveAcademicSupervisor}
          />
        ) : (
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn ghost"
              onClick={onAddAcademicSupervisor}
            >
              <Plus size={11} />
              {t("projectSettings.addAcademicSupervisor")}
            </button>
            <span className="dim" style={{ fontSize: 11 }}>
              {t("projectSettings.academicSupervisorHint")}
            </span>
          </div>
        )}
      </div>
    </SectionCard>
  );
};
