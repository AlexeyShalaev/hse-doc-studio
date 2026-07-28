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
          size={13}
          style={{ flexShrink: 0, color: "var(--fg-2)" }}
        />
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: 0,
            width: 300,
            maxHeight: 380,
            overflowY: "auto",
            zIndex: 50,
            padding: 6,
            background: "var(--bg-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-2, 8px)",
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
                  gap: 8,
                  width: "100%",
                  textAlign: "left",
                  padding: "7px 8px",
                  borderRadius: 6,
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
                      fontSize: 12.5,
                      fontWeight: 500,
                    }}
                  >
                    {persona.label}
                  </span>
                  <span
                    className="dim"
                    style={{ display: "block", fontSize: 11, lineHeight: 1.35 }}
                  >
                    {persona.description}
                  </span>
                </span>
              </button>
            );
          })}

          {customOpen && (
            <div style={{ padding: "6px 8px 4px" }}>
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
                  fontSize: 12,
                  padding: "6px 8px",
                  background: "var(--bg-0)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  color: "var(--fg-0)",
                }}
              />
              <div
                className="flex justify-end"
                style={{ gap: 6, marginTop: 6 }}
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
              gap: 6,
              width: "100%",
              marginTop: 4,
              padding: "7px 8px",
              border: "none",
              borderTop: "1px solid var(--border)",
              background: "transparent",
              cursor: "pointer",
              fontSize: 12,
              color: "var(--fg-2)",
            }}
            onClick={() => {
              setOpen(false);
              void navigate("/settings/agent-personas");
            }}
          >
            <Settings2 size={13} style={{ flexShrink: 0 }} />
            <span>{t("persona.manage")}</span>
          </button>
        </div>
      )}
    </div>
  );
};
