import { useLayoutEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AgentTool, Persona } from "@entities/agent-chat";
import { ChatToolsMenu } from "./ChatToolsMenu";
import { ModelPicker, type ModelProviderGroup } from "./ModelPicker";
import { PersonaPicker } from "./PersonaPicker";

export type ChatComposerSendOptions = {
  providerId?: string;
  model?: string;
};

type ChatComposerProps = {
  disabled: boolean;
  providerReady: boolean;
  running: boolean;
  // One compact model picker (Copilot-style): models grouped by provider, with
  // the long tail collapsed under "Другие модели".
  modelGroups: ModelProviderGroup[];
  selectedProviderId: string;
  selectedModel: string;
  autoApprove: boolean;
  controlsDisabled: boolean;
  tools: AgentTool[];
  enabledTools: string[] | null;
  // Agent role: available roles + the current selection (id + custom text).
  personas: Persona[];
  selectedPersona: string;
  personaInstructions: string;
  onModelSelect: (providerId: string, model: string) => void;
  onModeChange: (autoApprove: boolean) => void;
  onEnabledToolsChange: (enabled: string[] | null) => void;
  onPersonaSelect: (id: string, instructions?: string) => void;
  onSend: (text: string, options: ChatComposerSendOptions) => void;
  onStop: () => void;
};

const COMPOSER_MIN_HEIGHT = 42;
const COMPOSER_MAX_HEIGHT = 140;

export const ChatComposer = ({
  disabled,
  providerReady,
  running,
  modelGroups,
  selectedProviderId,
  selectedModel,
  autoApprove,
  controlsDisabled,
  tools,
  enabledTools,
  personas,
  selectedPersona,
  personaInstructions,
  onModelSelect,
  onModeChange,
  onEnabledToolsChange,
  onPersonaSelect,
  onSend,
  onStop,
}: ChatComposerProps) => {
  const { t } = useTranslation("agentChat");
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    const nextHeight = Math.min(
      Math.max(textarea.scrollHeight, COMPOSER_MIN_HEIGHT),
      COMPOSER_MAX_HEIGHT,
    );

    textarea.style.height = `${nextHeight.toString()}px`;
    textarea.style.overflowY =
      textarea.scrollHeight > COMPOSER_MAX_HEIGHT ? "auto" : "hidden";
  }, [text, disabled]);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled || !providerReady) return;
    const options: ChatComposerSendOptions = {};
    if (selectedProviderId) options.providerId = selectedProviderId;
    if (selectedModel) options.model = selectedModel;
    onSend(trimmed, options);
    setText("");
  };

  const sendDisabled = disabled || !providerReady || !text.trim();
  const placeholder = disabled
    ? t("composer.waitingForAgent")
    : providerReady
      ? t("composer.messageAgent")
      : t("composer.selectProvider");

  return (
    <div
      className="agent-composer-shell"
      style={{
        padding: 10,
        borderTop: "1px solid var(--border)",
        background: "var(--bg-0)",
      }}
    >
      <div className="agent-composer-box">
        <textarea
          ref={textareaRef}
          className="agent-composer-textarea mono"
          style={{
            minHeight: COMPOSER_MIN_HEIGHT,
            maxHeight: COMPOSER_MAX_HEIGHT,
          }}
          rows={1}
          value={text}
          placeholder={placeholder}
          title={t("composer.inputHint")}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />

        <div className="agent-composer-footer">
          <ModelPicker
            groups={modelGroups}
            selectedProviderId={selectedProviderId}
            selectedModel={selectedModel}
            disabled={controlsDisabled || modelGroups.length === 0}
            onSelect={onModelSelect}
          />

          {personas.length > 0 && (
            <PersonaPicker
              personas={personas}
              selectedPersona={selectedPersona}
              personaInstructions={personaInstructions}
              disabled={controlsDisabled}
              onSelect={onPersonaSelect}
            />
          )}

          <div
            className="agent-composer-mode"
            role="group"
            aria-label={t("composer.modeGroupLabel")}
          >
            <button
              type="button"
              className="agent-composer-mode-btn"
              data-active={!autoApprove ? "true" : undefined}
              disabled={controlsDisabled}
              onClick={() => {
                onModeChange(false);
              }}
            >
              Ask
            </button>
            <button
              type="button"
              className="agent-composer-mode-btn"
              data-active={autoApprove ? "true" : undefined}
              disabled={controlsDisabled}
              onClick={() => {
                onModeChange(true);
              }}
            >
              Auto
            </button>
          </div>
          {tools.length > 0 && (
            <ChatToolsMenu
              tools={tools}
              enabled={enabledTools}
              onChange={onEnabledToolsChange}
              disabled={controlsDisabled}
            />
          )}

          <div className="agent-composer-spacer" />

          {running ? (
            <button
              type="button"
              className="icon-btn agent-composer-action"
              onClick={onStop}
              title={t("composer.stop")}
            >
              <Square size={13} />
            </button>
          ) : (
            <button
              type="button"
              className="icon-btn agent-composer-action"
              onClick={submit}
              disabled={sendDisabled}
              title={t("composer.send")}
            >
              <Send size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
