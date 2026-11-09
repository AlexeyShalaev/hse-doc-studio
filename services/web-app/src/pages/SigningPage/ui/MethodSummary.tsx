import { useTranslation } from "react-i18next";
import type { SigningTask, SigningTaskAction } from "@entities/signing-route";
import { approveBlocker } from "../lib/signingState";

/**
 * «Как подписать» без подписи на странице: способ своих слотов и готовность картинки или
 * ключа для плашки. Где нужна подпись на самой странице (картинка, ключ, «Согласовать и
 * подписать», «Подписать»), стоит заглушка: её место займёт блок среза W5
 * (`SigningExtension.method`).
 */
export const MethodSummary = ({
  task,
  action,
}: {
  task: SigningTask;
  action: SigningTaskAction;
}) => {
  const { t } = useTranslation("signing");
  const { me } = task;
  const blocker = approveBlocker(me);
  const needsPage = action !== "approve" || blocker !== null;
  return (
    <section className="sgn-card" data-testid="signing-method">
      <h3>{t("method.title")}</h3>
      {me.method === null ? (
        <p>{t("method.approveOnly")}</p>
      ) : (
        <>
          <p>
            {t("method.current", { method: t(`method.name.${me.method}`) })}
          </p>
          {me.method === "image" ? (
            <p>
              {t(me.image_ready ? "method.imageReady" : "method.imageMissing")}
            </p>
          ) : me.plate ? (
            <p>
              {t("method.plateReady", {
                owner: me.plate.owner,
                kind: t(`method.plateKind.${me.plate.kind}`),
                id: me.plate.cert_id,
              })}
            </p>
          ) : (
            <p>{t("method.plateMissing")}</p>
          )}
        </>
      )}
      {needsPage && (
        <p className="sgn-placeholder" data-testid="signing-method-placeholder">
          {t("method.soon")}
        </p>
      )}
    </section>
  );
};
