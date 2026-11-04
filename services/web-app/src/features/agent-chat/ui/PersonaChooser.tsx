import { useState } from "react";
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Persona } from "@entities/agent-chat";
import { CUSTOM_PERSONA_ID, PersonaIcon } from "../lib/personaIcons";

type PersonaChooserProps = {
  personas: Persona[];
  selectedPersona: string;
  personaInstructions: string;
  onSelect: (id: string, instructions?: string) => void;
};

// The "choose your agent" screen shown for a fresh chat (no messages yet):
// a grid of role cards. Picking "Своя роль" reveals a textarea for a free-form
// instruction. Mirrors the compact PersonaPicker but as an inviting first screen.
export const PersonaChooser = ({
  personas,
  selectedPersona,
  personaInstructions,
  onSelect,
}: PersonaChooserProps) => {
  const { t } = useTranslation("agentChat");
  const [customDraft, setCustomDraft] = useState(personaInstructions);
  const [customOpen, setCustomOpen] = useState(
    selectedPersona === CUSTOM_PERSONA_ID,
  );
  // Keep the draft in sync when the inherited instructions change (render-phase
  // pattern — avoids a setState-in-effect).
  const [trackedInstructions, setTrackedInstructions] =
    useState(personaInstructions);
  if (personaInstructions !== trackedInstructions) {
    setTrackedInstructions(personaInstructions);
    setCustomDraft(personaInstructions);
  }

  const handleCard = (id: string) => {
    if (id === CUSTOM_PERSONA_ID) {
      setCustomOpen(true);
      return;
    }
    setCustomOpen(false);
    onSelect(id);
  };

  const applyCustom = () => {
    const text = customDraft.trim();
    if (!text) return;
    onSelect(CUSTOM_PERSONA_ID, text);
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "1.25rem 1rem" }}>
      <div style={{ textAlign: "center", marginBottom: "1rem" }}>
        <div style={{ fontSize: "0.875rem", fontWeight: 600 }}>
          {t("persona.chooserTitle")}
        </div>
        <div
          className="dim"
          style={{ fontSize: "0.75rem", marginTop: "0.25rem" }}
        >
          {t("persona.chooserSubtitle")}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.5rem",
        }}
      >
        {personas.map((persona) => {
          const isActive = persona.id === selectedPersona;
          return (
            <button
              key={persona.id}
              type="button"
              className="flex flex-col"
              style={{
                gap: "0.375rem",
                alignItems: "flex-start",
                textAlign: "left",
                padding: "0.625rem 0.625rem",
                borderRadius: "0.5rem",
                cursor: "pointer",
                background: isActive ? "var(--bg-hover)" : "var(--bg-1)",
                border: `1px solid ${isActive ? "var(--accent)" : "var(--border)"}`,
              }}
              onClick={() => {
                handleCard(persona.id);
              }}
            >
              <div
                className="flex items-center"
                style={{ gap: "0.375rem", width: "100%" }}
              >
                <PersonaIcon
                  id={persona.id}
                  builtin={persona.builtin}
                  size={15}
                  style={{
                    flexShrink: 0,
                    color: isActive ? "var(--accent)" : "var(--fg-2)",
                  }}
                />
                <span
                  style={{
                    fontSize: "0.78125rem",
                    fontWeight: 600,
                    minWidth: 0,
                  }}
                >
                  {persona.label}
                </span>
                {isActive && (
                  <Check
                    size="0.8125rem"
                    style={{ marginLeft: "auto", color: "var(--accent)" }}
                  />
                )}
              </div>
              <span
                className="dim"
                style={{ fontSize: "0.6875rem", lineHeight: 1.35 }}
              >
                {persona.description}
              </span>
            </button>
          );
        })}
      </div>

      {customOpen && (
        <div style={{ marginTop: "0.625rem" }}>
          <textarea
            className="mono"
            value={customDraft}
            placeholder={t("persona.customPlaceholder")}
            rows={4}
            autoFocus
            onChange={(e) => {
              setCustomDraft(e.target.value);
            }}
            style={{
              width: "100%",
              resize: "vertical",
              fontSize: "0.75rem",
              padding: "0.5rem 0.625rem",
              background: "var(--bg-0)",
              border: "1px solid var(--border)",
              borderRadius: "0.5rem",
              color: "var(--fg-0)",
            }}
          />
          <div className="flex justify-end" style={{ marginTop: "0.375rem" }}>
            <button
              type="button"
              className="btn xs"
              disabled={!customDraft.trim()}
              onClick={applyCustom}
            >
              {t("persona.applyRole")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
