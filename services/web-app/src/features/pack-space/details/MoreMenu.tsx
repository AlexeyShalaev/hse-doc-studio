import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { ActionMenu } from "@shared/ui";
import { useSpaceNav } from "../context/useSpaceNav";
import type { ConditionEdit } from "./edit/useConditionEdit";

type MoreMenuProps = {
  edit: ConditionEdit;
  historyOpen: boolean;
  onHistory: () => void;
};

/** «Ещё»: отменить и повторить правку, история правок, ссылка на этот элемент. */
export const MoreMenu = ({ edit, historyOpen, onHistory }: MoreMenuProps) => {
  const { t } = useTranslation("packSpace");
  const nav = useSpaceNav();
  const locked = edit.blocked !== null || edit.busy;
  return (
    <ActionMenu
      label={t("details.more.label")}
      testId="sp-more"
      items={[
        {
          id: "undo",
          label: t("details.more.undo"),
          disabled: !edit.canUndo || locked,
          onSelect: edit.undo,
          testId: "sp-more-undo",
        },
        {
          id: "redo",
          label: t("details.more.redo"),
          disabled: !edit.canRedo || locked,
          onSelect: edit.redo,
          testId: "sp-more-redo",
        },
        {
          id: "history",
          label: t("details.more.history"),
          checked: historyOpen,
          onSelect: onHistory,
          testId: "sp-more-history",
        },
        {
          id: "link",
          label: t("details.more.link"),
          onSelect: () => {
            const url = `${window.location.origin}${nav.href()}`;
            void navigator.clipboard.writeText(url).then(
              () => {
                toast.success(t("details.more.linkCopied"));
              },
              () => {
                toast.error(t("details.more.linkFailed"));
              },
            );
          },
          testId: "sp-more-link",
        },
      ]}
    />
  );
};
