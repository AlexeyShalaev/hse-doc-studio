import { useState } from "react";
import { useTranslation } from "react-i18next";
import { metaFieldDefault } from "@shared/lib/metaFields";
import { asString, asStrings, pickLocalized, type Raw } from "../../lib/raw";

/**
 * Живой образец поля (5.2): так его видит студент в мастере проекта и в
 * настройках: подпись со звёздочкой, если поле нужно при создании, подсказка
 * ввода, значение по умолчанию или вычисленное (`auto`), текст помощи.
 */
export const FieldSample = ({
  fieldKey,
  spec,
}: {
  fieldKey: string;
  spec: Raw;
}) => {
  const { t, i18n } = useTranslation("packForms");
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const type = asString(spec.type) || "string";
  const label = pickLocalized(spec.label, lang, fieldKey);
  const help = pickLocalized(spec.help, lang);
  const required = asString(spec.required_at) === "create";
  const seeded =
    metaFieldDefault({
      type,
      default: spec.default,
      auto: asString(spec.auto) || null,
    }) ?? "";
  const [value, setValue] = useState<string | null>(null);
  const shown = value ?? seeded;
  const options = asStrings(spec.options);

  let control;
  if (type === "bool") {
    control = (
      <label className="pf-check">
        <input type="checkbox" defaultChecked={spec.default === true} />
        <span>{label}</span>
      </label>
    );
  } else if (type === "person") {
    control = <p className="pf-hint">{t("fields.samplePerson")}</p>;
  } else if (type === "select" || (type === "font" && options.length > 0)) {
    control = (
      <select
        className="input"
        value={shown}
        aria-label={label}
        onChange={(e) => {
          setValue(e.target.value);
        }}
      >
        <option value="">—</option>
        {!options.includes(shown) && shown && (
          <option value={shown}>{shown}</option>
        )}
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  } else {
    control = (
      <input
        type="text"
        className="input"
        aria-label={label}
        placeholder={asString(spec.placeholder)}
        value={shown}
        onChange={(e) => {
          setValue(e.target.value);
        }}
      />
    );
  }

  return (
    <div className="pf-sample" data-testid="field-sample">
      <div className="pf-sample-title">{t("fields.sample")}</div>
      <div className="field" style={{ gap: "0.25rem" }}>
        {type !== "bool" && (
          <label>
            {label}
            {required && <span className="pf-required">*</span>}
          </label>
        )}
        {control}
        {help && <div className="hint">{help}</div>}
      </div>
    </div>
  );
};
