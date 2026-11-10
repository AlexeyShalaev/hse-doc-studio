import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { FilePen, FileDiff } from "lucide-react";
import { pickLocalized } from "@shared/lib";
import { Button } from "@shared/ui";
import {
  checkpointPath,
  type SigningTask,
  type SigningTaskDoc,
} from "@entities/signing-route";
import { formatMoment } from "../lib/format";
import {
  divergenceOf,
  newVersionDocs,
  type SigningStatus,
} from "../lib/signingState";

const useDocNames = () => {
  const { t, i18n } = useTranslation("signing");
  return (docs: readonly SigningTaskDoc[]): string =>
    docs
      .map((doc) =>
        t("newVersion.quote", {
          name: pickLocalized(doc.name, i18n.language, doc.doc_id),
        }),
      )
      .join(", ");
};

/**
 * «Новая версия: изменился документ …» (раздел 12.2, подписант): автор отправил новую версию,
 * в своей очередь подписант действует только по изменившимся документам. Сообщение маршрута
 * («Что изменилось», если автор его заполнил) показывается здесь, а не в шапке.
 */
export const NewVersionNotice = ({
  task,
  status,
}: {
  task: SigningTask;
  status: SigningStatus;
}) => {
  const { t } = useTranslation("signing");
  const names = useDocNames();
  const docs = newVersionDocs(task);
  if (!docs) return null;
  // Повторить нужно только то, где сервер дал отпечаток: согласованное заново уже не просят.
  const again =
    status.kind === "turn" ? docs.filter((doc) => doc.token !== null) : [];
  return (
    <section
      className="sgn-notice"
      data-testid="signing-new-version"
      aria-label={t("newVersion.label")}
    >
      <p>
        <FilePen size="0.9375rem" aria-hidden />
        <span>
          {t("newVersion.changed", { count: docs.length, names: names(docs) })}
          {status.kind === "turn" && again.length > 0 && (
            <>
              {" "}
              {t(`newVersion.again.${status.action}`, { count: again.length })}
            </>
          )}
        </span>
      </p>
      {task.route.message && (
        <blockquote
          className="sgn-message"
          aria-label={t("head.message")}
          data-testid="signing-message"
        >
          {task.route.message}
        </blockquote>
      )}
    </section>
  );
};

/**
 * Плашка расхождения у автора и управляющего маршрутом (раздел 12.2, п. 3 и 5): рабочая
 * сборка ушла от версии на подписи. Подписанты этого не видят, маршрут идёт дальше; новую
 * версию отправляют из карточки «Подписание».
 */
export const DivergenceBanner = ({ task }: { task: SigningTask }) => {
  const { t } = useTranslation("signing");
  const names = useDocNames();
  const divergence = divergenceOf(task);
  if (!divergence) return null;
  const base = divergence.completed ? "completed" : "active";
  const text = divergence.sentAt
    ? t(`divergence.${base}`, { date: formatMoment(divergence.sentAt) })
    : t(`divergence.${base}NoDate`);
  return (
    <section
      className="sgn-notice"
      data-tone="warn"
      data-testid="signing-divergence"
      aria-label={t("divergence.label")}
    >
      <p>
        <FileDiff size="0.9375rem" aria-hidden />
        <span>
          {text}
          {task.docs.length > 1 && (
            <>
              {" "}
              {t("divergence.docs", {
                count: divergence.docs.length,
                names: names(divergence.docs),
              })}
            </>
          )}
        </span>
      </p>
      <div>
        <Button asChild size="sm" variant="secondary">
          <Link
            to={checkpointPath(task.route.project.id, task.route.profile.id)}
            data-testid="signing-send-new-version"
          >
            {t("divergence.send")}
          </Link>
        </Button>
      </div>
    </section>
  );
};
