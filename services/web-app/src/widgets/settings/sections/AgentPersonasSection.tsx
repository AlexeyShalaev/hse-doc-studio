import { useState } from "react";
import { Copy, Drama, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useBuiltinPersonas,
  useCustomPersonas,
  useDeletePersona,
  type AgentPersona,
  type BuiltinPersona,
} from "@entities/agent-persona";
import {
  AgentPersonaEditorModal,
  type PersonaDraft,
} from "@features/manage-agent-persona";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { SettingHead } from "./Setting";

type RoleRowProps = {
  label: string;
  description: string;
  badge?: string;
  children: React.ReactNode;
};

const RoleRow = ({ label, description, badge, children }: RoleRowProps) => (
  <div
    className="flex items-center justify-between"
    style={{
      gap: "0.75rem",
      padding: "0.625rem 0.75rem",
      borderRadius: "0.375rem",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    <div className="flex flex-col" style={{ gap: "0.25rem", minWidth: 0 }}>
      <div className="flex items-center" style={{ gap: "0.5rem" }}>
        <Drama
          size="0.8125rem"
          style={{ color: "var(--fg-2)", flexShrink: 0 }}
        />
        <span style={{ fontSize: "0.78125rem", fontWeight: 500 }}>{label}</span>
        {badge && (
          <span
            className="mono"
            style={{
              fontSize: "0.625rem",
              padding: "1px 0.375rem",
              borderRadius: "0.1875rem",
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {badge}
          </span>
        )}
      </div>
      {description && (
        <div className="dim" style={{ fontSize: "0.6875rem" }}>
          {description}
        </div>
      )}
    </div>
    <div
      className="flex items-center"
      style={{ gap: "0.375rem", flexShrink: 0 }}
    >
      {children}
    </div>
  </div>
);

export const AgentPersonasSection = () => {
  const { t } = useTranslation("settings");
  const builtinsQuery = useBuiltinPersonas();
  const customQuery = useCustomPersonas();
  const deletePersona = useDeletePersona();

  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<PersonaDraft | null>(null);

  const builtins = builtinsQuery.data ?? [];
  const custom = customQuery.data ?? [];

  const openCreate = () => {
    setDraft(null);
    setEditorOpen(true);
  };

  const openEdit = (persona: AgentPersona) => {
    setDraft({
      id: persona.id,
      label: persona.label,
      description: persona.description,
      instruction: persona.instruction,
    });
    setEditorOpen(true);
  };

  const openDuplicate = (persona: BuiltinPersona | AgentPersona) => {
    // No id → the editor creates a new custom role from the prefilled values.
    setDraft({
      label: t("agentPersonas.copySuffix", { label: persona.label }),
      description: persona.description,
      instruction: persona.instruction,
    });
    setEditorOpen(true);
  };

  const handleDelete = (persona: AgentPersona) => {
    if (
      !window.confirm(
        t("agentPersonas.deleteConfirm", { label: persona.label }),
      )
    )
      return;
    deletePersona.mutate(persona.id, {
      onSuccess: () => {
        toast.success(
          t("agentPersonas.deletedToast", { label: persona.label }),
        );
      },
    });
  };

  return (
    <>
      <SettingHead
        anchorId="agent-personas"
        title={t("agentPersonas.title")}
        sub={t("agentPersonas.subtitle")}
      />

      <div
        className="flex flex-col"
        style={{ gap: "1rem", paddingBottom: "0.875rem" }}
      >
        <div
          id="agent-personas-custom"
          className="flex flex-col settings-anchor"
          style={{ gap: "0.5rem" }}
        >
          <div
            className="dim"
            style={{
              fontSize: "0.625rem",
              textTransform: "uppercase",
              letterSpacing: "0.03125rem",
            }}
          >
            {t("agentPersonas.yourRoles")}
          </div>
          {customQuery.isLoading ? (
            <div
              className="flex items-center"
              style={{ gap: "0.5rem", fontSize: "0.75rem" }}
            >
              <Spinner size="sm" />
              <span className="dim">{t("agentPersonas.loadingRoles")}</span>
            </div>
          ) : custom.length === 0 ? (
            <div className="dim" style={{ fontSize: "0.75rem" }}>
              {t("agentPersonas.noCustomRoles")}
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: "0.375rem" }}>
              {custom.map((persona) => (
                <RoleRow
                  key={persona.id}
                  label={persona.label}
                  description={persona.description}
                >
                  <button
                    type="button"
                    className="btn xs"
                    title={t("agentPersonas.duplicate")}
                    onClick={() => {
                      openDuplicate(persona);
                    }}
                  >
                    <Copy size="0.6875rem" />
                  </button>
                  <button
                    type="button"
                    className="btn xs"
                    title={t("agentPersonas.edit")}
                    onClick={() => {
                      openEdit(persona);
                    }}
                  >
                    <Pencil size="0.6875rem" />
                  </button>
                  <button
                    type="button"
                    className="btn xs"
                    title={t("agentPersonas.delete")}
                    disabled={deletePersona.isPending}
                    onClick={() => {
                      handleDelete(persona);
                    }}
                  >
                    <Trash2 size="0.6875rem" />
                  </button>
                </RoleRow>
              ))}
            </div>
          )}

          <div>
            <button type="button" className="btn xs" onClick={openCreate}>
              <Plus size="0.6875rem" />
              {t("agentPersonas.createRole")}
            </button>
          </div>
        </div>

        <div
          id="agent-personas-builtin"
          className="flex flex-col settings-anchor"
          style={{ gap: "0.5rem" }}
        >
          <div
            className="dim"
            style={{
              fontSize: "0.625rem",
              textTransform: "uppercase",
              letterSpacing: "0.03125rem",
            }}
          >
            {t("agentPersonas.builtinRoles")}
          </div>
          <div className="flex flex-col" style={{ gap: "0.375rem" }}>
            {builtins.map((persona) => (
              <RoleRow
                key={persona.id}
                label={persona.label}
                description={persona.description}
                badge={t("agentPersonas.builtinBadge")}
              >
                <button
                  type="button"
                  className="btn xs"
                  title={t("agentPersonas.duplicateToCustomTitle")}
                  onClick={() => {
                    openDuplicate(persona);
                  }}
                >
                  <Copy size="0.6875rem" />
                  {t("agentPersonas.duplicateLabel")}
                </button>
              </RoleRow>
            ))}
          </div>
        </div>
      </div>

      {editorOpen && (
        <AgentPersonaEditorModal
          key={draft?.id ?? draft?.label ?? "new"}
          isOpen={editorOpen}
          persona={draft}
          onClose={() => {
            setEditorOpen(false);
          }}
        />
      )}
    </>
  );
};
