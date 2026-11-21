import { Check } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { CLASS_KEYS } from "./notesDraft";
import type { SubmitController } from "./useSubmit";

/**
 * Галочка «Выпустить версию X» (pack-studio-ux.md, 5.6): выпуск встаёт перед отправкой, одной
 * кнопкой вместо двух шагов. Рядом словами написано, какого размера правка и как сменить номер;
 * сверка и «версия по умолчанию» спрятаны под «Дополнительно».
 */
export const ReleaseOption = ({
  c,
  onNumber,
}: {
  c: SubmitController;
  onNumber: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const uid = useId();
  const { state } = c;
  if (!state) return null;
  const cls = c.releaseClass;
  return (
    <div className="sp-sb-block" data-testid="sp-sb-release">
      <div className="sp-sb-release">
        <label className="sp-sb-check" htmlFor={`${uid}-release`}>
          <input
            id={`${uid}-release`}
            type="checkbox"
            checked={c.release}
            disabled={!c.releasable || c.running}
            onChange={(e) => {
              c.setRelease(e.target.checked);
            }}
            data-testid="sp-sb-release-input"
          />
          <span>
            {t("changes.submit.release.label", {
              version: state.version.version,
            })}
          </span>
        </label>
        <span className="sp-ch-muted sp-sb-release-meta">
          {cls
            ? `${t(`changes.submit.class.${CLASS_KEYS[cls]}`).toLowerCase()} · `
            : ""}
          <button
            type="button"
            className="sp-ch-link"
            disabled={c.running}
            onClick={onNumber}
            data-testid="sp-sb-number"
          >
            {t("changes.submit.release.number")}
          </button>
        </span>
      </div>
      <p className="sp-ch-muted">{t("changes.submit.release.lead")}</p>
      {!state.number_ok && (
        <p className="sp-sb-warn" role="status" data-testid="sp-sb-number-bad">
          {t("changes.submit.release.numberBad", {
            version: state.minimum ? (state.numbers[state.minimum] ?? "") : "",
          })}
        </p>
      )}
      {state.release_outdated && (
        <p className="sp-ch-muted" data-testid="sp-sb-outdated">
          <Check size="0.75rem" aria-hidden="true" />{" "}
          {t("changes.submit.release.outdated")}
        </p>
      )}
      <details className="sp-sb-more">
        <summary>{t("changes.submit.release.advanced")}</summary>
        <div className="sp-sb-more-body">
          {state.base && (
            <p className="sp-ch-muted">
              {t("changes.submit.release.base", { version: state.base })}
            </p>
          )}
          <label className="sp-sb-check" htmlFor={`${uid}-default`}>
            <input
              id={`${uid}-default`}
              type="checkbox"
              checked={c.setDefault}
              disabled={c.running}
              onChange={(e) => {
                c.setSetDefault(e.target.checked);
              }}
              data-testid="sp-sb-default-input"
            />
            <span>{t("changes.submit.release.setDefault")}</span>
          </label>
        </div>
      </details>
    </div>
  );
};
