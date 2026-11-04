import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { ChevronDown, Settings2 } from "lucide-react";
import type { Persona } from "@entities/agent-chat";
import { CUSTOM_PERSONA_ID, PersonaIcon } from "../lib/personaIcons";

type PersonaPickerProps = {
  personas: Persona[];
  selectedPersona: string;
  personaInstructions: string;
  disabled?: boolean;
  onSelect: (id: string, instructions?: string) => void;
};

// Compact role pill for the composer footer (mirrors ModelPicker): a popover
// list of agent roles; picking "Своя роль" reveals a textarea for a free-form
// instruction. Selection is persisted on the chat session by the parent.
export const PersonaPicker = ({
  personas,
  selectedPersona,
  personaInstructions,
  disabled = false,
  onSelect,
}: PersonaPickerProps) => {
  const { t } = useTranslation("agentChat");
  const [open, setOpen] = useState(false);
  const [customDraft, setCustomDraft] = useState(personaInstructions);
  const [customOpen, setCustomOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (rootRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const active =
    personas.find((p) => p.id === selectedPersona) ??
    personas.find((p) => p.id === "default");

  const openMenu = () => {
    setCustomDraft(personaInstructions);
    setCustomOpen(selectedPersona === CUSTOM_PERSONA_ID);
    setOpen((v) => !v);
  };

  const pick = (id: string) => {
    if (id === CUSTOM_PERSONA_ID) {
      setCustomOpen(true);
      return;
    }
    onSelect(id);
    setOpen(false);
  };

  const applyCustom = () => {
    const text = customDraft.trim();
    if (!text) return;
    onSelect(CUSTOM_PERSONA_ID, text);
    setOpen(false);
  };

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        disabled={disabled}
        className="agent-composer-modelbtn"
        title={
          active
            ? t("persona.roleTitle", { name: active.label })
            : t("persona.selectRole")
        }
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          if (!disabled) openMenu();
        }}
      >
        <PersonaIcon
          id={active?.id ?? "default"}
          builtin={active?.builtin ?? true}
          size={13}
          style={{ flexShrink: 0, color: "var(--accent)" }}
        />
        <span className="truncate">
          {active?.label ?? t("persona.fallbackLabel")}
        </span>
        <ChevronDown
          size="0.8125rem"
          style={{ flexShrink: 0, color: "var(--fg-2)" }}
        />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            bottom: "calc(100% + 0.375rem)",
            left: 0,
            width: "18.75rem",
            maxHeight: "23.75rem",
            overflowY: "auto",
            zIndex: 50,
            padding: "0.375rem",
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-2, 0.5rem)",
            boxShadow: "var(--shadow-elev, 0 8px 24px rgba(0,0,0,0.3))",
          }}
        >
          {personas.map((persona) => {
            const isActive = persona.id === selectedPersona;
            return (
              <button
                key={persona.id}
                type="button"
                className="flex items-start"
                style={{
                  gap: "0.5rem",
                  width: "100%",
                  textAlign: "left",
                  padding: "0.4375rem 0.5rem",
                  borderRadius: "0.375rem",
                  background: isActive ? "var(--bg-hover)" : "transparent",
                  border: "none",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => {
                  if (!isActive)
                    e.currentTarget.style.background = "var(--bg-hover)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive)
                    e.currentTarget.style.background = "transparent";
                }}
                onClick={() => {
                  pick(persona.id);
                }}
              >
                <PersonaIcon
                  id={persona.id}
                  builtin={persona.builtin}
                  size={15}
                  style={{
                    flexShrink: 0,
                    marginTop: 1,
                    color: isActive ? "var(--accent)" : "var(--fg-2)",
                  }}
                />
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      display: "block",
                      fontSize: "0.78125rem",
                      fontWeight: 500,
                    }}
                  >
                    {persona.label}
                  </span>
                  <span
                    className="dim"
                    style={{
                      display: "block",
                      fontSize: "0.6875rem",
                      lineHeight: 1.35,
                    }}
                  >
                    {persona.description}
                  </span>
                </span>
              </button>
            );
          })}

          {customOpen && (
            <div style={{ padding: "0.375rem 0.5rem 0.25rem" }}>
              <textarea
                className="mono"
                value={customDraft}
                placeholder={t("persona.customPlaceholder")}
                rows={3}
                autoFocus
                onChange={(e) => {
                  setCustomDraft(e.target.value);
                }}
                style={{
                  width: "100%",
                  resize: "vertical",
                  fontSize: "0.75rem",
                  padding: "0.375rem 0.5rem",
                  background: "var(--bg-0)",
                  border: "1px solid var(--border)",
                  borderRadius: "0.375rem",
                  color: "var(--fg-0)",
                }}
              />
              <div
                className="flex justify-end"
                style={{ gap: "0.375rem", marginTop: "0.375rem" }}
              >
                <button
                  type="button"
                  className="btn xs"
                  disabled={!customDraft.trim()}
                  onClick={applyCustom}
                >
                  {t("persona.apply")}
                </button>
              </div>
            </div>
          )}

          <button
            type="button"
            className="flex items-center"
            style={{
              gap: "0.375rem",
              width: "100%",
              marginTop: "0.25rem",
              padding: "0.4375rem 0.5rem",
              border: "none",
              borderTop: "1px solid var(--border)",
              background: "transparent",
              cursor: "pointer",
              fontSize: "0.75rem",
              color: "var(--fg-2)",
            }}
            onClick={() => {
              setOpen(false);
              void navigate("/settings/agent-personas");
            }}
          >
            <Settings2 size="0.8125rem" style={{ flexShrink: 0 }} />
            <span>{t("persona.manage")}</span>
          </button>
        </div>
      )}
    </div>
  );
};
