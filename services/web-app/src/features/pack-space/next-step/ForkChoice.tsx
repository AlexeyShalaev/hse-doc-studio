import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@shared/ui";
import type { SubmitController } from "./useSubmit";

/**
 * Что делать, когда в репозиторий писать нельзя (pack-studio-ux.md, 5.6, 5.10): отправить в
 * свою копию репозитория (форк). Создать её самим токеном можно на GitHub, иначе человек
 * указывает адрес своей копии.
 */
export const ForkChoice = ({
  c,
  serviceAccess,
}: {
  c: SubmitController;
  serviceAccess: boolean;
}) => {
  const { t } = useTranslation("packSpace");
  const uid = useId();
  const { fork } = c;
  if (!fork) return null;
  const canCreate = fork.canCreate && !serviceAccess;
  const useUrl = c.forkMode === "url" || !canCreate;
  return (
    <div className="sp-sb-block" data-testid="sp-sb-fork">
      <h3 className="sp-ch-h">{t("submit.fork.title")}</h3>
      <p className="sp-ch-muted">{t("submit.fork.lead")}</p>
      {fork.reason && (
        <p className="sp-sb-warn" role="alert">
          {t(`submit.fork.reason.${fork.reason}`, {
            defaultValue: t("submit.fork.reasonOther"),
          })}
        </p>
      )}
      {canCreate && (
        <>
          <label className="sp-sb-choice" htmlFor={`${uid}-create`}>
            <input
              id={`${uid}-create`}
              type="radio"
              name={`${uid}-fork`}
              checked={c.forkMode === "create"}
              disabled={c.running}
              onChange={() => {
                c.setForkMode("create");
              }}
              data-testid="sp-sb-fork-create"
            />
            <span className="sp-sb-choice-text">
              <span>{t("submit.fork.create")}</span>
              <span className="sp-sb-choice-hint">
                {t("submit.fork.createHint")}
              </span>
            </span>
          </label>
          <label className="sp-sb-choice" htmlFor={`${uid}-own`}>
            <input
              id={`${uid}-own`}
              type="radio"
              name={`${uid}-fork`}
              checked={c.forkMode === "url"}
              disabled={c.running}
              onChange={() => {
                c.setForkMode("url");
              }}
            />
            <span className="sp-sb-choice-text">
              <span>{t("submit.fork.own")}</span>
              <span className="sp-sb-choice-hint">
                {t("submit.fork.ownHint")}
              </span>
            </span>
          </label>
        </>
      )}
      {useUrl && (
        <Input
          label={t("submit.fork.url")}
          hint={t("submit.fork.urlHint")}
          placeholder="https://github.com/me/packs.git"
          value={c.forkUrl}
          maxLength={2048}
          disabled={c.running}
          onChange={(e) => {
            c.setForkUrl(e.target.value);
          }}
          isMono
          data-testid="sp-sb-fork-url"
        />
      )}
    </div>
  );
};
