import { useState } from "react";
import { Building2, UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { SEARCH_DEBOUNCE_MS, toast, useDebouncedValue } from "@shared/lib";
import {
  Button,
  ConfirmByName,
  Input,
  Modal,
  Spinner,
  Textarea,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  useStartTransfer,
  useTransferCandidates,
  type TransferCandidate,
} from "@entities/invitation";
import { useInvitationFailureText } from "@features/project-invitations";

export type TransferDialogProps = {
  projectId: string;
  projectName: string;
  isOpen: boolean;
  onClose: () => void;
};

/** Передать проект (10.8): человеку с подтверждением, организации сразу после ввода имени проекта. */
export const TransferDialog = ({
  projectId,
  projectName,
  isOpen,
  onClose,
}: TransferDialogProps) => {
  const { t } = useTranslation("invitations");
  const failureText = useInvitationFailureText();
  const [query, setQuery] = useState("");
  const needle = useDebouncedValue(query.trim(), SEARCH_DEBOUNCE_MS);
  const candidates = useTransferCandidates(projectId, needle, isOpen);
  const [target, setTarget] = useState<TransferCandidate | null>(null);
  const [message, setMessage] = useState("");
  const [confirmOrg, setConfirmOrg] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = useStartTransfer(projectId);

  const reset = () => {
    setQuery("");
    setTarget(null);
    setMessage("");
    setConfirmOrg(false);
    setError(null);
  };
  const close = () => {
    reset();
    onClose();
  };

  const send = (confirmName: string | null) => {
    if (!target) return;
    setError(null);
    start.mutate(
      {
        to_kind: target.kind,
        to_id: target.id,
        message: message.trim() === "" ? null : message.trim(),
        confirm_name: confirmName,
      },
      {
        onSuccess: () => {
          toast.success(
            target.kind === "org"
              ? t("transfer.doneOrg", { name: target.name })
              : t("transfer.sent", { name: target.name }),
          );
          close();
        },
        onError: (e) => {
          setConfirmOrg(false);
          setError(failureText(failureCode(e)));
        },
      },
    );
  };

  if (confirmOrg && target) {
    return (
      <ConfirmByName
        isOpen
        onClose={() => {
          setConfirmOrg(false);
        }}
        onConfirm={() => {
          send(projectName);
        }}
        name={projectName}
        title={t("transfer.orgConfirmTitle", { name: target.name })}
        description={t("transfer.orgHint", { name: target.name })}
        confirmLabel={t("transfer.submit")}
        pending={start.isPending}
      />
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      width={520}
      title={t("transfer.dialogTitle")}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={close}>
            {t("form.cancel")}
          </Button>
          <Button
            type="button"
            disabled={!target || start.isPending}
            data-testid="transfer-submit"
            onClick={() => {
              if (target?.kind === "org") setConfirmOrg(true);
              else send(null);
            }}
          >
            {t("transfer.submit")}
          </Button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="transfer-dialog"
      >
        <label className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          {t("transfer.target")}
          <Input
            value={query}
            placeholder={t("transfer.search")}
            onChange={(e) => {
              setQuery(e.target.value);
            }}
            data-testid="transfer-search"
          />
        </label>
        <ul
          className="flex flex-col"
          style={{ listStyle: "none", margin: 0, padding: 0, gap: 2 }}
          data-testid="transfer-target"
          role="listbox"
          aria-label={t("transfer.target")}
        >
          {candidates.isFetching && !candidates.data && <Spinner size="sm" />}
          {(candidates.data?.items ?? []).map((c) => {
            const Icon = c.kind === "org" ? Building2 : UserRound;
            const selected = target?.kind === c.kind && target.id === c.id;
            return (
              <li key={`${c.kind}:${c.id}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className="flex items-center"
                  data-testid={`transfer-target-${c.kind}-${c.id}`}
                  style={{
                    gap: 10,
                    width: "100%",
                    padding: "6px 8px",
                    borderRadius: "var(--r-2)",
                    border: selected
                      ? "1px solid var(--accent)"
                      : "1px solid transparent",
                    background: selected ? "var(--bg-2)" : "transparent",
                    color: "var(--fg-0)",
                    textAlign: "left",
                  }}
                  onClick={() => {
                    setTarget(c);
                  }}
                >
                  <Icon size={14} aria-hidden="true" />
                  <span style={{ fontSize: 13 }}>{c.name}</span>
                  {c.detail && (
                    <span className="dim" style={{ fontSize: 11.5 }}>
                      {c.detail}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
          {candidates.data?.items.length === 0 && (
            <li className="dim" style={{ fontSize: 12 }}>
              {t("transfer.none")}
            </li>
          )}
        </ul>
        {target && (
          <Notice
            tone={target.kind === "org" ? "warn" : "info"}
            text={
              target.kind === "org"
                ? t("transfer.orgHint", { name: target.name })
                : t("transfer.userHint")
            }
          />
        )}
        <label className="flex flex-col" style={{ gap: 4, fontSize: 12 }}>
          {t("form.message")}
          <Textarea
            value={message}
            rows={2}
            maxLength={1000}
            onChange={(e) => {
              setMessage(e.target.value);
            }}
          />
        </label>
        {error && (
          <div role="alert">
            <Notice tone="err" text={error} />
          </div>
        )}
      </div>
    </Modal>
  );
};
