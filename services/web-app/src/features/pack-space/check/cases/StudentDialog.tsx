import { useTranslation } from "react-i18next";
import { usePackOutcome } from "@entities/pack-studio";
import { StudentView } from "./student/StudentView";
import { Modal, Spinner } from "@shared/ui";
import { WordsOverlay } from "../WordsOverlay";
import { Notice } from "../Notice";
import type { CheckEnv } from "../useCheckEnv";

/**
 * «Так увидит студент»: комплект и подписи при условиях самого готового случая, как их увидит
 * студент проекта (документы, что заполнить, кто подписывает). Разметку и данные даёт прежний вид
 * «Как студент», слова в нём по словарю нового интерфейса (`check.student.words`).
 */
export const StudentDialog = ({
  env,
  caseId,
  name,
  onClose,
}: {
  env: CheckEnv;
  caseId: string;
  name: string;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const outcome = usePackOutcome(env.workspaceId, env.ref, {
    state: "work_tree",
    scenario: caseId,
  });
  return (
    <Modal
      isOpen
      onClose={onClose}
      width={720}
      title={t("check.student.title")}
      description={t("check.student.lead", { name })}
    >
      <div data-testid="case-student">
        {outcome.data ? (
          <WordsOverlay path="check.student.words">
            <StudentView outcome={outcome.data} />
          </WordsOverlay>
        ) : outcome.isError ? (
          <Notice
            tone="error"
            title={t("check.student.failed")}
            actions={
              <button
                type="button"
                className="btn sm"
                onClick={() => void outcome.refetch()}
              >
                {t("check.retry")}
              </button>
            }
          />
        ) : (
          <p className="sp-ck-loading" role="status">
            <Spinner size="sm" />
            {t("check.student.loading")}
          </p>
        )}
      </div>
    </Modal>
  );
};
