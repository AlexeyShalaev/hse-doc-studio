import { useId } from "react";
import { useTranslation } from "react-i18next";
import type { LicenseInfo } from "./submitErrors";

/**
 * Согласие с лицензией перед первой отправкой в официальные шаблоны (template-studio.md, 4.7):
 * вклад публичен и идёт под лицензией репозитория, запрос уйдёт от аккаунта человека.
 */
export const LicenseConsent = ({
  info,
  checked,
  disabled,
  onChange,
}: {
  info: LicenseInfo;
  checked: boolean;
  disabled: boolean;
  onChange: (value: boolean) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const uid = useId();
  return (
    <div className="sp-sb-block" data-testid="sp-sb-license">
      <label className="sp-sb-choice" htmlFor={`${uid}-license`}>
        <input
          id={`${uid}-license`}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => {
            onChange(e.target.checked);
          }}
          data-testid="sp-sb-license-accept"
        />
        <span className="sp-sb-choice-text">
          <span>
            {t("changes.submit.license.consent", {
              license:
                info.license !== ""
                  ? info.license
                  : t("changes.submit.license.repoLicense"),
            })}
          </span>
          <span className="sp-sb-choice-hint">
            {t("changes.submit.license.hint")}
          </span>
        </span>
      </label>
      {(info.licenseUrl ?? info.contributingUrl) !== null && (
        <span className="sp-sb-links">
          {info.licenseUrl && (
            <a href={info.licenseUrl} target="_blank" rel="noopener noreferrer">
              {t("changes.submit.license.license")}
            </a>
          )}
          {info.contributingUrl && (
            <a
              href={info.contributingUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("changes.submit.license.rules")}
            </a>
          )}
        </span>
      )}
      <p className="sp-ch-muted">{t("changes.submit.license.afterMerge")}</p>
    </div>
  );
};
