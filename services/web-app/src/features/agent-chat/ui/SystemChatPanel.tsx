import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import type { TFunction } from "i18next";
import {
  Bot,
  Bug,
  History,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useAgentTools } from "@entities/agent-chat";
import { useAIProviders } from "@entities/ai-provider";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { requirementsKeys } from "@entities/requirements";
import {
  systemAgentApi,
  systemAgentKeys,
  useAgentPersonas,
  useAnswerSystemTurn,
  useApproveSystemTurn,
  useCancelSystemTurn,
  useCreateSystemChat,
  useDeleteSystemChat,
  useRenameSystemChat,
  useStartSystemTurn,
  useSystemChat,
  useSystemChats,
  useUpdateSystemChat,
} from "@entities/system-agent";
import { vcsKeys } from "@entities/vcs";
import { localeTag, useWorkspaceStore } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { applyAgentToolEffect } from "../lib/applyAgentToolEffect";
import { useAgentRunStream } from "../lib/useAgentRunStream";
import { ChatApprovalBar } from "./ChatApprovalBar";
import { ChatComposer } from "./ChatComposer";
import { ChatDebugPanel } from "./ChatDebugPanel";
import { ChatMessages } from "./ChatMessages";
import { ChatQuestionForm } from "./ChatQuestionForm";
import { PersonaChooser } from "./PersonaChooser";

type SystemChatPanelProps = {
  width?: number;
  onClose: () => void;
  // Current project from the route (if any). New chats bind to it so the agent
  // gets project tools + context; absent → a global/system chat.
  projectId?: string;
};

const formatChatAge = (
  updatedAt: string,
  t: TFunction<"agentChat">,
  language: string,
): string => {
  const timestamp = new Date(updatedAt).getTime();
  const diffMs = Date.now() - timestamp;
  if (!Number.isFinite(timestamp) || diffMs < 0) return "";

  const minutes = Math.max(1, Math.floor(diffMs / 60_000));
  if (minutes < 60) return t("history.ageMinutes", { count: minutes });

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("history.ageHours", { count: hours });

  const days = Math.floor(hours / 24);
  if (days < 7) return t("history.ageDays", { count: days });

  return new Date(updatedAt).toLocaleDateString(language, {
    day: "2-digit",
    month: "2-digit",
  });
};

export const SystemChatPanel = ({
  width = 400,
  onClose,
  projectId,
}: SystemChatPanelProps) => {
  const { t } = useTranslation("agentChat");
  const queryClient = useQueryClient();
  const sessionsQuery = useSystemChats();
  const providersQuery = useAIProviders();
  const settingsQuery = useAppSettings();
  const updateSettings = useUpdateAppSettings();
  const toolsQuery = useAgentTools();
  const personasQuery = useAgentPersonas();
  const updateSession = useUpdateSystemChat();
  // The agent adapts to context: in a project it has the full catalog
  // ("проект с расширением"); outside one the backend only ever runs the
  // app/system tools. `agent_enabled_tools` is a single global preference, so
  // the Configure-Tools menu always shows the whole catalog (filtering it here
  // would silently drop hidden project-tool selections on toggle).
  const inProject = Boolean(projectId);
  const tools = toolsQuery.data ?? [];
  const enabledTools = settingsQuery.data?.agent_enabled_tools ?? null;
  const pendingPrompt = useWorkspaceStore((state) => state.pendingPrompt);
  const consumePendingPrompt = useWorkspaceStore(
    (state) => state.consumePendingPrompt,
  );
  const sessions = sessionsQuery.data ?? [];

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const historyRootRef = useRef<HTMLDivElement | null>(null);
  const [composerProviderId, setComposerProviderId] = useState<string | null>(
    null,
  );
  const [composerModel, setComposerModel] = useState<string | null>(null);
  const [composerAutoApprove, setComposerAutoApprove] = useState<
    boolean | null
  >(null);
  const [composerPersona, setComposerPersona] = useState<string | null>(null);
  const [composerPersonaInstructions, setComposerPersonaInstructions] =
    useState<string | null>(null);
  const [trackedSessionId, setTrackedSessionId] = useState<string | null>(null);

  const activeId = selectedId ?? sessions[0]?.id ?? null;
  const activeSession = sessions.find((session) => session.id === activeId);
  // Drop the composer's role override when switching chats so each chat shows
  // its own stored persona (render-phase reset — avoids a setState-in-effect).
  if (activeId !== trackedSessionId) {
    setTrackedSessionId(activeId);
    setComposerPersona(null);
    setComposerPersonaInstructions(null);
  }
  const filteredSessions = sessions.filter((session) =>
    session.title.toLowerCase().includes(historyQuery.trim().toLowerCase()),
  );

  const detailQuery = useSystemChat(activeId);
  const activeRunId = detailQuery.data?.active_run_id ?? null;
  const messages = detailQuery.data?.messages ?? [];

  const providers = providersQuery.data ?? [];
  const sessionProviderId = detailQuery.data?.default_provider_id ?? null;
  const settingsProviderId = settingsQuery.data?.default_ai_provider_id ?? null;
  const preferredProviderId =
    composerProviderId ?? sessionProviderId ?? settingsProviderId ?? "";
  const settingsProvider =
    settingsProviderId !== null
      ? providers.find((provider) => provider.id === settingsProviderId)
      : undefined;
  const selectedProvider =
    providers.find((provider) => provider.id === preferredProviderId) ??
    settingsProvider ??
    providers[0] ??
    null;
  const selectedProviderId = selectedProvider?.id ?? "";
  const sessionModel = detailQuery.data?.default_model ?? null;
  const settingsModel = settingsQuery.data?.default_ai_model ?? null;
  const preferredModel =
    composerModel ??
    (selectedProviderId === sessionProviderId ? sessionModel : null) ??
    (selectedProviderId === settingsProviderId ? settingsModel : null) ??
    "";
  const selectedModel =
    selectedProvider?.models.includes(preferredModel) === true
      ? preferredModel
      : (selectedProvider?.models[0] ?? "");
  const providerReady = selectedProvider !== null && selectedModel !== "";
  // One compact model picker: all providers' models grouped by provider.
  const modelGroups = providers
    .map((provider) => ({
      providerId: provider.id,
      providerName: provider.name,
      models: provider.models,
    }))
    .filter((group) => group.models.length > 0);
  const autoApprove =
    composerAutoApprove ??
    settingsQuery.data?.agent_auto_approve_writes ??
    false;
  // Agent role layered like the model: composer override → this session's stored
  // persona → the sticky default from settings → neutral.
  const personas = personasQuery.data ?? [];
  const selectedPersona =
    composerPersona ??
    detailQuery.data?.persona ??
    settingsQuery.data?.default_agent_persona ??
    "default";
  const personaInstructions =
    composerPersonaInstructions ??
    detailQuery.data?.persona_instructions ??
    settingsQuery.data?.default_agent_persona_instructions ??
    "";

  const createSession = useCreateSystemChat();
  const deleteSession = useDeleteSystemChat();
  const renameSession = useRenameSystemChat();
  const startTurn = useStartSystemTurn();
  const approveTurn = useApproveSystemTurn();
  const answerTurn = useAnswerSystemTurn();
  const cancelTurn = useCancelSystemTurn();

  const [runId, setRunId] = useState<string | null>(null);
  const connectedRunRef = useRef<string | null>(null);

  const refetchDetail = (sessionId: string | null) => {
    void queryClient.invalidateQueries({
      queryKey: systemAgentKeys.detail(sessionId ?? ""),
    });
  };
  const refetchSessions = () => {
    void queryClient.invalidateQueries({ queryKey: systemAgentKeys.list() });
  };

  const stream = useAgentRunStream({
    onMessage: () => {
      refetchDetail(activeId);
    },
    onDone: () => {
      refetchDetail(activeId);
      refetchSessions();
    },
    onToolResult: (name, args, isError) => {
      // App-control tools (e.g. set_theme) only persist server-side; mirror the
      // change into the client theme store so it takes effect live (the visible
      // theme is driven by that store, not by the backend settings).
      if (!isError) applyAgentToolEffect(name, args);
      // VCS tools (snapshot/restore) change project history server-side; refresh
      // the «Версии» view so the timeline/status/branches reflect it live.
      if (!isError && name.startsWith("vcs_") && projectId) {
        void queryClient.invalidateQueries({
          queryKey: [...vcsKeys.all, "status", projectId],
        });
        void queryClient.invalidateQueries({
          queryKey: [...vcsKeys.all, "history", projectId],
        });
        void queryClient.invalidateQueries({
          queryKey: vcsKeys.branches(projectId),
        });
        void queryClient.invalidateQueries({
          queryKey: vcsKeys.tags(projectId),
        });
      }
      // Applying a requirements format rebuilds the traceability matrix
      // server-side; refresh the «Трассировка требований» view + format editor.
      if (!isError && name === "set_requirements_format" && projectId) {
        void queryClient.invalidateQueries({
          queryKey: requirementsKeys.matrix(projectId),
        });
      }
    },
  });
  const { start: beginStream, reset: resetStream } = stream;

  const running = stream.state.status === "running";
  const awaiting = stream.state.status === "awaiting_approval";
  const pendingQuestion = stream.state.questions[0] ?? null;
  const composerControlsDisabled =
    running || awaiting || providersQuery.isLoading || settingsQuery.isLoading;

  useEffect(() => {
    if (!historyOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (historyRootRef.current?.contains(target)) return;
      setHistoryOpen(false);
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [historyOpen]);

  const startStream = useCallback(
    (rid: string, sessionId: string) => {
      setRunId(rid);
      connectedRunRef.current = rid;
      beginStream(systemAgentApi.streamUrl(sessionId, rid));
    },
    [beginStream],
  );

  useEffect(() => {
    connectedRunRef.current = null;
  }, [activeId]);

  // Reconnect to an in-flight run after the panel was closed / page reloaded.
  useEffect(() => {
    if (!activeId || !activeRunId) return;
    if (connectedRunRef.current === activeRunId) return;
    startStream(activeRunId, activeId);
  }, [activeId, activeRunId, startStream]);

  const handleModelSelect = (providerId: string, model: string) => {
    setComposerProviderId(providerId || null);
    setComposerModel(model || null);
    updateSettings.mutate({
      default_ai_provider_id: providerId || null,
      default_ai_model: model || null,
    });
  };
  const handleModeChange = (nextAutoApprove: boolean) => {
    setComposerAutoApprove(nextAutoApprove);
    updateSettings.mutate({ agent_auto_approve_writes: nextAutoApprove });
  };
  const handleEnabledToolsChange = (enabled: string[] | null) => {
    updateSettings.mutate({ agent_enabled_tools: enabled });
  };
  const handlePersonaSelect = (id: string, instructions?: string) => {
    const text = instructions ?? null;
    setComposerPersona(id);
    setComposerPersonaInstructions(text);
    // Persist on this chat (drives the next turn's system prompt) and as the
    // sticky default new chats inherit.
    if (activeId !== null) {
      updateSession.mutate({
        sessionId: activeId,
        body: { persona: id, persona_instructions: text },
      });
    }
    updateSettings.mutate({
      default_agent_persona: id,
      default_agent_persona_instructions: text,
    });
  };

  const handleSend = (text: string) => {
    if (activeId === null) return;
    const sessionId = activeId;
    startTurn.mutate(
      {
        sessionId,
        body: {
          text,
          ...(selectedProviderId ? { provider_id: selectedProviderId } : {}),
          ...(selectedModel ? { model: selectedModel } : {}),
        },
      },
      {
        onSuccess: (res) => {
          refetchDetail(sessionId);
          refetchSessions();
          startStream(res.run_id, sessionId);
        },
      },
    );
  };

  const handleApprove = (callIds: string[]) => {
    if (activeId === null || runId === null) return;
    const sessionId = activeId;
    approveTurn.mutate(
      { sessionId, runId, callIds },
      {
        onSuccess: (res) => {
          startStream(res.run_id, sessionId);
        },
      },
    );
  };

  const handleAnswer = (callId: string, answers: Record<string, string>) => {
    if (activeId === null || runId === null) return;
    const sessionId = activeId;
    answerTurn.mutate(
      { sessionId, runId, answers: { [callId]: answers } },
      {
        onSuccess: (res) => {
          startStream(res.run_id, sessionId);
        },
      },
    );
  };

  const handleStop = () => {
    if (activeId !== null && runId !== null)
      cancelTurn.mutate({ sessionId: activeId, runId });
    resetStream();
  };
  const handleReject = () => {
    handleStop();
    refetchDetail(activeId);
  };

  const handleNewChat = () => {
    createSession.mutate(
      {
        ...(projectId ? { project_id: projectId } : {}),
        ...(selectedProviderId ? { provider_id: selectedProviderId } : {}),
        ...(selectedModel ? { model: selectedModel } : {}),
        // Seed the new chat with the inherited (sticky) role.
        ...(selectedPersona !== "default" ? { persona: selectedPersona } : {}),
        ...(selectedPersona === "custom" && personaInstructions
          ? { persona_instructions: personaInstructions }
          : {}),
      },
      {
        onSuccess: (session) => {
          resetStream();
          setSelectedId(session.id);
          setHistoryOpen(false);
        },
      },
    );
  };

  const handleDeleteChat = (sessionId: string) => {
    if (!window.confirm(t("panel.deleteConfirm"))) return;
    deleteSession.mutate(sessionId, {
      onSuccess: () => {
        if (sessionId === activeId) {
          resetStream();
          setSelectedId(null);
        }
      },
    });
  };

  const handleSelectSession = (id: string) => {
    resetStream();
    setSelectedId(id || null);
    setHistoryOpen(false);
  };

  const handleStartRename = (id: string, title: string) => {
    setRenamingId(id);
    setRenameDraft(title);
  };
  const handleCommitRename = () => {
    if (renamingId === null) return;
    const title = renameDraft.trim();
    if (!title) {
      setRenamingId(null);
      setRenameDraft("");
      return;
    }
    renameSession.mutate(
      { sessionId: renamingId, title },
      {
        onSuccess: () => {
          refetchSessions();
          setRenamingId(null);
          setRenameDraft("");
        },
      },
    );
  };

  // A prompt queued from elsewhere (e.g. "fix this build"/"fix this finding")
  // is auto-sent here once a chat is ready. Refs keep the trigger effect
  // dependency-light (mirrors ChatPanel).
  const autoSendRef = useRef<((text: string) => void) | null>(null);
  const ensureSessionRef = useRef<(() => void) | null>(null);
  const creatingForPromptRef = useRef(false);
  useEffect(() => {
    autoSendRef.current = (text: string) => {
      handleSend(text);
    };
    ensureSessionRef.current = handleNewChat;
  });
  const readyToAutoSend =
    activeId !== null &&
    providerReady &&
    !running &&
    !awaiting &&
    !startTurn.isPending;
  // A queued prompt fired from a project context (e.g. "Подобрать с ИИ", fix
  // build/findings) must run in a chat bound to THAT project, else its
  // project-scoped tools (set_requirements_format, compile, …) aren't advertised
  // and it would target the wrong project. If the current chat is a different/no
  // project, start a fresh project-bound one instead of auto-sending to it.
  const needsNewProjectChat =
    projectId != null &&
    activeSession != null &&
    (activeSession.project_id ?? null) !== projectId;
  useEffect(() => {
    if (!pendingPrompt) {
      creatingForPromptRef.current = false;
      return;
    }
    if (activeId === null || needsNewProjectChat) {
      if (sessionsQuery.isLoading || creatingForPromptRef.current) return;
      creatingForPromptRef.current = true;
      ensureSessionRef.current?.();
      return;
    }
    if (!readyToAutoSend) return;
    creatingForPromptRef.current = false;
    const text = consumePendingPrompt();
    if (text) autoSendRef.current?.(text);
  }, [
    pendingPrompt,
    activeId,
    needsNewProjectChat,
    readyToAutoSend,
    sessionsQuery.isLoading,
    consumePendingPrompt,
  ]);

  const usage = stream.state.usage;

  return (
    <div
      className="system-chat-panel flex flex-col"
      style={{
        width,
        flexShrink: 0,
        borderLeft: "1px solid var(--border)",
        background: "var(--bg-0)",
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{
          gap: 8,
          padding: "8px 10px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div className="flex items-center min-w-0" style={{ gap: 6 }}>
          <Bot size={15} style={{ color: "var(--accent)", flexShrink: 0 }} />
          <span
            className="truncate"
            style={{ fontSize: 13, fontWeight: 600 }}
            title={activeSession?.title}
          >
            {inProject ? t("panel.titleProject") : t("panel.titleAssistant")}
          </span>
        </div>
        <div
          ref={historyRootRef}
          className="chat-panel-actions"
          style={{ position: "relative" }}
        >
          <button
            type="button"
            className="icon-btn"
            title={t("panel.newChat")}
            onClick={handleNewChat}
          >
            <Plus size={15} />
          </button>
          <button
            type="button"
            className={clsx("icon-btn", historyOpen && "active")}
            title={t("panel.history")}
            onClick={() => {
              setHistoryOpen((open) => !open);
            }}
          >
            <History size={15} />
          </button>
          <button
            type="button"
            className={clsx("icon-btn", debugOpen && "active")}
            title={t("panel.debug")}
            onClick={() => {
              setDebugOpen((v) => !v);
            }}
          >
            <Bug size={14} />
          </button>
          <button
            type="button"
            className="icon-btn"
            title={t("panel.close")}
            onClick={onClose}
          >
            <X size={14} />
          </button>

          {historyOpen && (
            <div className="chat-history-popover">
              <div className="chat-history-search">
                <Search size={13} />
                <input
                  type="text"
                  value={historyQuery}
                  onChange={(e) => {
                    setHistoryQuery(e.target.value);
                  }}
                  placeholder={t("history.searchPlaceholder")}
                />
              </div>

              <div className="chat-history-list">
                {filteredSessions.length === 0 ? (
                  <div className="chat-history-empty">
                    {sessions.length === 0
                      ? t("history.empty")
                      : t("history.notFound")}
                  </div>
                ) : (
                  filteredSessions.map((session) => {
                    const isRenaming = session.id === renamingId;
                    return (
                      <div
                        key={session.id}
                        className={clsx(
                          "chat-history-row",
                          session.id === activeId && "active",
                        )}
                      >
                        {isRenaming ? (
                          <input
                            className="chat-history-rename"
                            value={renameDraft}
                            autoFocus
                            onChange={(e) => {
                              setRenameDraft(e.target.value);
                            }}
                            onBlur={handleCommitRename}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleCommitRename();
                              if (e.key === "Escape") {
                                setRenamingId(null);
                                setRenameDraft("");
                              }
                            }}
                          />
                        ) : (
                          <button
                            type="button"
                            className="chat-history-title"
                            onClick={() => {
                              handleSelectSession(session.id);
                            }}
                          >
                            {session.is_running && (
                              <span
                                className="dot live"
                                style={{ flexShrink: 0 }}
                                title={t("history.running")}
                              />
                            )}
                            <span>{session.title}</span>
                            <span className="chat-history-meta">
                              {formatChatAge(
                                session.updated_at,
                                t,
                                localeTag(),
                              )}
                            </span>
                          </button>
                        )}

                        {!isRenaming && (
                          <div className="chat-history-row-actions">
                            <button
                              type="button"
                              className="icon-btn sm"
                              title={t("history.rename")}
                              onClick={() => {
                                handleStartRename(session.id, session.title);
                              }}
                            >
                              <Pencil size={12} />
                            </button>
                            <button
                              type="button"
                              className="icon-btn sm"
                              title={t("history.delete")}
                              onClick={() => {
                                handleDeleteChat(session.id);
                              }}
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {sessionsQuery.isLoading ? (
        <div
          className="flex items-center justify-center"
          style={{ flex: 1, gap: 8, fontSize: 12 }}
        >
          <Spinner size="sm" />
          <span className="dim">{t("panel.loading")}</span>
        </div>
      ) : activeId === null ? (
        <div
          className="flex flex-col items-center justify-center"
          style={{ flex: 1, gap: 10, padding: 20 }}
        >
          <span className="dim" style={{ fontSize: 12, textAlign: "center" }}>
            {inProject
              ? t("panel.emptyProjectHint")
              : t("panel.emptyAssistantHint")}
          </span>
          <button type="button" className="btn xs" onClick={handleNewChat}>
            <Plus size={11} />
            {t("panel.newChatShort")}
          </button>
        </div>
      ) : (
        <>
          {messages.length === 0 &&
          !running &&
          !awaiting &&
          !stream.state.liveText &&
          personas.length > 0 ? (
            <PersonaChooser
              personas={personas}
              selectedPersona={selectedPersona}
              personaInstructions={personaInstructions}
              onSelect={handlePersonaSelect}
            />
          ) : (
            <ChatMessages
              messages={messages}
              liveText={stream.state.liveText}
              running={running}
              projectId={projectId ?? ""}
            />
          )}
          {stream.state.error && (
            <div
              style={{
                padding: "6px 12px",
                fontSize: 11.5,
                color: "var(--c-err)",
              }}
            >
              {stream.state.error}
            </div>
          )}
          {pendingQuestion ? (
            <ChatQuestionForm
              pending={pendingQuestion}
              submitting={answerTurn.isPending}
              onSubmit={handleAnswer}
            />
          ) : (
            awaiting && (
              <ChatApprovalBar
                approvals={stream.state.approvals}
                pending={approveTurn.isPending}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            )
          )}
          {debugOpen && (
            <ChatDebugPanel
              debug={stream.state.debug}
              lastEventAt={stream.state.lastEventAt}
              status={stream.state.status}
              running={running}
              runId={runId}
              model={selectedModel}
              provider={selectedProvider?.name}
            />
          )}
          <ChatComposer
            disabled={running || awaiting}
            providerReady={providerReady}
            running={running}
            modelGroups={modelGroups}
            selectedProviderId={selectedProviderId}
            selectedModel={selectedModel}
            autoApprove={autoApprove}
            controlsDisabled={composerControlsDisabled}
            tools={tools}
            enabledTools={enabledTools}
            personas={personas}
            selectedPersona={selectedPersona}
            personaInstructions={personaInstructions}
            onModelSelect={handleModelSelect}
            onModeChange={handleModeChange}
            onEnabledToolsChange={handleEnabledToolsChange}
            onPersonaSelect={handlePersonaSelect}
            onSend={handleSend}
            onStop={handleStop}
          />
          {usage && (
            <div
              className="dim mono"
              style={{ fontSize: 10, padding: "2px 10px 6px" }}
            >
              {t("panel.tokens", {
                total: usage.total,
                input: usage.input,
                output: usage.output,
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
};
