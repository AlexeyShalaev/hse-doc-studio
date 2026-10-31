import { useState } from "react";
import { MailPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import { InviteDialog } from "./InviteDialog";

/** «Пригласить научрука» (10.6): та же форма с ролью Рецензент и персоной научного руководителя. */
export const InviteSupervisorButton = ({
  projectId,
  persona = "supervisor",
}: {
  projectId: string;
  persona?: string;
}) => {
  const { t } = useTranslation("invitations");
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        style={{ gap: 6 }}
        data-testid="invite-supervisor"
        onClick={() => {
          setOpen(true);
        }}
      >
        <MailPlus size={12} aria-hidden="true" />
        {t("supervisor.invite")}
      </Button>
      <InviteDialog
        projectId={projectId}
        isOpen={open}
        onClose={() => {
          setOpen(false);
        }}
        preset={{ role: "reviewer", persona }}
      />
    </>
  );
};
