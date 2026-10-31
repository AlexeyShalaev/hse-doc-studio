import { useState } from "react";
import { ArrowRightLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Button } from "@shared/ui";
import type { ProjectRole } from "@entities/session";
import {
  useCancelTransfer,
  useProjectTransfer,
  type ProjectTransferState,
} from "@entities/invitation";
import { useInvitationFailureText } from "@features/project-invitations";
import { TransferDialog } from "./TransferDialog";

const BOX = {
  padding: 12,
  border: "1px solid color-mix(in oklch, var(--c-err) 30%, var(--border))",
  borderRadius: "var(--r-2)",
  gap: 12,
} as const;

export type TransferSectionViewProps = {
  state: ProjectTransferState | undefined;
  lang?: string;
  busy?: boolean;
  onStart: () => void;
  onCancel: () => void;
};

export const TransferSectionView = ({
  state,
  lang = "ru",
  busy = false,
  onStart,
  onCancel,
}: TransferSectionViewProps) => {
  const { t } = useTranslation("invitations");
  const pending = state?.transfer ?? null;
  return (
    <div
      className="flex items-center justify-between"
      style={BOX}
      data-testid="project-transfer"
      data-state={pending ? "pending" : "none"}
    >
      <div className="flex flex-col" style={{ gap: 2 }}>
        <strong style={{ fontSize: 12.5 }}>{t("transfer.title")}</strong>
        <span className="dim" style={{ fontSize: 11 }}>
          {pending
            ? t("transfer.pending", {
                name: pending.to.name,
                date: new Date(pending.expires_at).toLocaleDateString(
                  lang === "en" ? "en-GB" : "ru-RU",
                  { day: "2-digit", month: "2-digit" },
                ),
              })
            : t("transfer.hint")}
        </span>
      </div>
      {pending ? (
        <Button
          type="button"
          variant="secondary"
          disabled={busy}
          data-testid="project-transfer-cancel"
          onClick={onCancel}
        >
          {t("transfer.cancel")}
        </Button>
      ) : (
        <Button
          type="button"
          variant="danger"
          style={{ gap: 6 }}
          data-testid="project-transfer-start"
          onClick={onStart}
        >
          <ArrowRightLeft size={11} aria-hidden="true" />
          {t("transfer.start")}
        </Button>
      )}
    </div>
  );
};

/** Блок «Передать проект» в опасной зоне: только владельцу (10.8). */
export const TransferSection = ({
  projectId,
  projectName,
  myRole,
}: {
  projectId: string;
  projectName: string;
  myRole: ProjectRole | null;
}) => {
  const { t, i18n } = useTranslation("invitations");
  const failureText = useInvitationFailureText();
  const isOwner = myRole === "owner";
  const state = useProjectTransfer(projectId, isOwner);
  const cancel = useCancelTransfer(projectId);
  const [open, setOpen] = useState(false);
  if (!isOwner) return null;
  return (
    <>
      <TransferSectionView
        state={state.data}
        lang={i18n.language}
        busy={cancel.isPending}
        onStart={() => {
          setOpen(true);
        }}
        onCancel={() => {
          cancel.mutate(undefined, {
            onSuccess: () => {
              toast.success(t("transfer.cancelled"));
            },
            onError: (e) => {
              toast.error(failureText(failureCode(e)));
            },
          });
        }}
      />
      <TransferDialog
        projectId={projectId}
        projectName={projectName}
        isOpen={open}
        onClose={() => {
          setOpen(false);
        }}
      />
    </>
  );
};
