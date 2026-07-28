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
      gap: 12,
      padding: "10px 12px",
      borderRadius: 6,
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
    }}
  >
    <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
      <div className="flex items-center" style={{ gap: 8 }}>
        <Drama size={13} style={{ color: "var(--fg-2)", flexShrink: 0 }} />
        <span style={{ fontSize: 12.5, fontWeight: 500 }}>{label}</span>
        {badge && (
          <span
            className="mono"
            style={{
              fontSize: 10,
              padding: "1px 6px",
              borderRadius: 3,
              background: "var(--bg-3)",
              color: "var(--fg-2)",
            }}
          >
            {badge}
          </span>
        )}
      </div>
      {description && (
        <div className="dim" style={{ fontSize: 11 }}>
          {description}
        </div>
      )}
    </div>
    <div className="flex items-center" style={{ gap: 6, flexShrink: 0 }}>
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

      <div className="flex flex-col" style={{ gap: 16, paddingBottom: 14 }}>
        <div
          id="agent-personas-custom"
          className="flex flex-col settings-anchor"
          style={{ gap: 8 }}
        >
          <div
            className="dim"
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            {t("agentPersonas.yourRoles")}
          </div>
          {customQuery.isLoading ? (
            <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
              <Spinner size="sm" />
              <span className="dim">{t("agentPersonas.loadingRoles")}</span>
            </div>
          ) : custom.length === 0 ? (
            <div className="dim" style={{ fontSize: 12 }}>
              {t("agentPersonas.noCustomRoles")}
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: 6 }}>
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
                    <Copy size={11} />
                  </button>
                  <button
                    type="button"
                    className="btn xs"
                    title={t("agentPersonas.edit")}
                    onClick={() => {
                      openEdit(persona);
                    }}
                  >
                    <Pencil size={11} />
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
                    <Trash2 size={11} />
                  </button>
                </RoleRow>
              ))}
            </div>
          )}

          <div>
            <button type="button" className="btn xs" onClick={openCreate}>
              <Plus size={11} />
              {t("agentPersonas.createRole")}
            </button>
          </div>
        </div>

        <div
          id="agent-personas-builtin"
          className="flex flex-col settings-anchor"
          style={{ gap: 8 }}
        >
          <div
            className="dim"
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            {t("agentPersonas.builtinRoles")}
          </div>
          <div className="flex flex-col" style={{ gap: 6 }}>
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
                  <Copy size={11} />
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
