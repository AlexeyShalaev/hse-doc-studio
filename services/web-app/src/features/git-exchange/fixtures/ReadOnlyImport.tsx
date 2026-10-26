import { useTranslation } from "react-i18next";
import { GALLERY_PROJECT_ID } from "@shared/lib/stateGallery";
import { BundleImportDialog } from "../ui/BundleImportDialog";

// Причина берётся из словаря: так же её называет карточка в настройках.
export const ReadOnlyImport = ({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) => {
  const { t } = useTranslation("gitExchange");
  return (
    <BundleImportDialog
      isOpen={isOpen}
      projectId={GALLERY_PROJECT_ID}
      onClose={onClose}
      disabledReason={t("card.import.readOnly")}
    />
  );
};
