import { useState } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import {
  CreateAgentPersonaSchema,
  useCreatePersona,
  useUpdatePersona,
} from "@entities/agent-persona";
import { Button } from "@shared/ui/Button";
import { toast } from "@shared/lib";

// Draft a persona is opened with: an existing role (has `id` → edit) or a
// prefilled-but-idless draft (→ create, e.g. duplicating a built-in).
export type PersonaDraft = {
  id?: string;
  label: string;
  description: string;
  instruction: string;
};

type AgentPersonaEditorModalProps = {
  isOpen: boolean;
  onClose: () => void;
  // null → create a blank role; a draft → edit (with id) or create (without id).
  persona?: PersonaDraft | null;
};

export const AgentPersonaEditorModal = ({
  isOpen,
  onClose,
  persona,
}: AgentPersonaEditorModalProps) => {
  const { t } = useTranslation("agentPersona");
  const isEdit = Boolean(persona?.id);
  const createPersona = useCreatePersona();
  const updatePersona = useUpdatePersona();

  // Initialised from props: the caller mounts this fresh per open (keyed by id),
  // so there is no stale state to reset.
  const [label, setLabel] = useState(persona?.label ?? "");
  const [description, setDescription] = useState(persona?.description ?? "");
  const [instruction, setInstruction] = useState(persona?.instruction ?? "");
  const [error, setError] = useState<string | null>(null);

  const isPending = createPersona.isPending || updatePersona.isPending;

  const handleSubmit = () => {
    setError(null);

    if (isEdit && persona?.id) {
      const trimmedLabel = label.trim();
      const trimmedInstruction = instruction.trim();
      if (!trimmedLabel) {
        setError(t("validation.nameRequired"));
        return;
      }
      if (!trimmedInstruction) {
        setError(t("validation.instructionRequired"));
        return;
      }
      updatePersona.mutate(
        {
          id: persona.id,
          body: {
            label: trimmedLabel,
            description: description.trim(),
            instruction: trimmedInstruction,
          },
        },
        {
          onSuccess: (updated) => {
            toast.success(t("toast.saved", { label: updated.label }));
            onClose();
          },
        },
      );
      return;
    }

    const parsed = CreateAgentPersonaSchema.safeParse({
      label: label.trim(),
      instruction: instruction.trim(),
      description: description.trim(),
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? t("validation.checkFields"));
      return;
    }
    createPersona.mutate(parsed.data, {
      onSuccess: (created) => {
        toast.success(t("toast.added", { label: created.label }));
        onClose();
      },
    });
  };

  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/2 z-[102] -translate-x-1/2 -translate-y-1/2"
          style={{ width: "30rem", maxWidth: "calc(100vw - 2rem)" }}
        >
          <DialogPrimitive.Description className="sr-only">
            {t("editor.srDescription")}
          </DialogPrimitive.Description>

          <div
            className="flex items-center justify-between"
            style={{
              padding: "0.75rem 1.125rem",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <DialogPrimitive.Title
              style={{ fontSize: "0.875rem", fontWeight: 600, margin: 0 }}
            >
              {isEdit ? t("editor.titleEdit") : t("editor.titleCreate")}
            </DialogPrimitive.Title>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              title={t("editor.close")}
            >
              <X size="0.875rem" />
            </button>
          </div>

          <div style={{ padding: "1.125rem", overflowY: "auto" }}>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("editor.labelName")}
                </label>
                <input
                  className="input"
                  value={label}
                  placeholder={t("editor.labelNamePlaceholder")}
                  onChange={(e) => {
                    setLabel(e.target.value);
                  }}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("editor.labelDescription")}{" "}
                  <span className="dim">
                    {t("editor.labelDescriptionOptional")}
                  </span>
                </label>
                <input
                  className="input"
                  value={description}
                  placeholder={t("editor.labelDescriptionPlaceholder")}
                  onChange={(e) => {
                    setDescription(e.target.value);
                  }}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("editor.labelInstruction")}
                </label>
                <textarea
                  className="input"
                  value={instruction}
                  placeholder={t("editor.labelInstructionPlaceholder")}
                  rows={6}
                  style={{ resize: "vertical", minHeight: "7.5rem" }}
                  onChange={(e) => {
                    setInstruction(e.target.value);
                  }}
                />
                <span className="hint">{t("editor.instructionHint")}</span>
              </div>

              {error && <span className="text-xs text-c-err">{error}</span>}
            </div>
          </div>

          <div
            className="flex items-center justify-end"
            style={{
              gap: "0.5rem",
              padding: "0.625rem 1.125rem",
              borderTop: "1px solid var(--border)",
            }}
          >
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={isPending}
            >
              {t("editor.cancel")}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={isPending}>
              {isEdit ? t("editor.save") : t("editor.create")}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
