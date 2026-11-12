import { useTranslation } from "react-i18next";
import type { SigningTask } from "@entities/signing-route";

/**
 * «Как подписать» без блока подписи: способ своих слотов и готовность картинки или ключа
 * для плашки. Страница показывает его согласующему без слотов и там, где расширение
 * (`SigningExtension.method`) не подключено.
 */
export const MethodSummary = ({ task }: { task: SigningTask }) => {
  const { t } = useTranslation("signing");
  const { me } = task;
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
            <p>{t(me.image_ready ? "image.ready" : "image.missing")}</p>
          ) : me.plate ? (
            <p>
              {t("method.plateReady", {
                owner: me.plate.owner,
                kind: t(`method.plateKind.${me.plate.kind}`),
                id: me.plate.cert_id,
              })}
            </p>
          ) : (
            <p>{t("esign.plateMissing")}</p>
          )}
        </>
      )}
    </section>
  );
};
