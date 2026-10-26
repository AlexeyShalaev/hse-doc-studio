import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui/Modal";
import { ExchangeCard } from "./ExchangeCard";

export type BundleExchangeDialogProps = {
  isOpen: boolean;
  projectId: string;
  onClose: () => void;
};

// «Обмен файлом» без захода в настройки: открывают со страницы истории, где
// репозитория ещё нет. Внутри та же карточка с выгрузкой и загрузкой, что и в
// настройках проекта, её диалоги открываются поверх этого.
export const BundleExchangeDialog = ({
  isOpen,
  projectId,
  onClose,
}: BundleExchangeDialogProps) => {
  const { t } = useTranslation("gitExchange");
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      width={560}
      title={t("dialog.title")}
    >
      <ExchangeCard projectId={projectId} />
    </Modal>
  );
};
