import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Modal, Select } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useProjectRoleLabel } from "@entities/project";
import { useDecideAccessRequest, type GrantRole } from "@entities/invitation";
import { useFailureText } from "../lib/failure";
import { usePersonaOptions } from "../lib/personas";

const ROLES: readonly GrantRole[] = ["reader", "reviewer", "editor"];

export type ApproveDialogProps = {
  projectId: string;
  request: { id: string; name: string } | null;
  onClose: () => void;
};

/** Одобрение запроса доступа: роль, персона (участник записывается сразу, согласие уже дано). */
export const ApproveDialog = ({
  projectId,
  request,
  onClose,
}: ApproveDialogProps) => {
  const { t } = useTranslation("invitations");
  const roleLabel = useProjectRoleLabel();
  const personas = usePersonaOptions(projectId);
  const failureText = useFailureText();
  const decide = useDecideAccessRequest(projectId);
  const [role, setRole] = useState<GrantRole>("reviewer");
  const [persona, setPersona] = useState("__none");
  const [error, setError] = useState<string | null>(null);

  return (
    <Modal
      isOpen={request !== null}
      onClose={onClose}
      title={t("requests.approveTitle", { name: request?.name ?? "" })}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("form.cancel")}
          </Button>
          <Button
            type="button"
            disabled={decide.isPending}
            data-testid="access-request-approve-submit"
            onClick={() => {
              if (!request) return;
              setError(null);
              decide.mutate(
                {
                  requestId: request.id,
                  approve: {
                    role,
                    persona: persona === "__none" ? null : persona,
                    can_share: false,
                    show_sources: true,
                    can_edit_all: false,
                  },
                },
                {
                  onSuccess: () => {
                    toast.success(
                      t("requests.approved", {
                        name: request.name,
                        role: roleLabel(role),
                      }),
                    );
                    onClose();
                  },
                  onError: (e) => {
                    setError(failureText(failureCode(e)));
                  },
                },
              );
            }}
          >
            {t("requests.approve")}
          </Button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="access-request-approve-form"
      >
        <div className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          {t("form.role")}
          <Select
            ariaLabel={t("form.role")}
            value={role}
            options={ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
            onValueChange={(next) => {
              setRole(next as GrantRole);
            }}
          />
        </div>
        <div className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          {t("form.persona")}
          <Select
            ariaLabel={t("form.persona")}
            value={persona}
            options={personas.map((p) => ({
              value: p.value === "" ? "__none" : p.value,
              label: p.label,
            }))}
            onValueChange={setPersona}
          />
        </div>
        {error && (
          <div role="alert">
            <Notice tone="err" text={error} />
          </div>
        )}
      </div>
    </Modal>
  );
};
