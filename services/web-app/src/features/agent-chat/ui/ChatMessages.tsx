import { useEffect, useMemo, useRef, useState } from "react";

import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { useNavigate } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { useDocuments } from "@entities/document";

import {
  buildDocRefIndex,
  docHrefForId,
  docIdFromHref,
  isDocHref,
  remarkDocLinks,
} from "../lib/docLinks";
import { stripToolCallNoise } from "../lib/sanitizeAssistantText";

import type { ChatContentBlock, ChatMessage } from "@entities/agent-chat";
import type { Components, Options, UrlTransform } from "react-markdown";
import type { DocRefIndex } from "../lib/docLinks";

type ChatMessagesProps = {
  messages: ChatMessage[];
  liveText: string;
  running: boolean;
  projectId: string;
};

const ROLE_LABEL_KEY: Record<string, string> = {
  user: "messages.roleUser",
  assistant: "messages.roleAssistant",
  tool: "messages.roleTool",
};

// While streaming, keep pinning to the latest token only if the user is within
// this many px of the bottom; past that they've scrolled up to read, so leave
// their position alone.
const BOTTOM_STICK_THRESHOLD_PX = 80;

export const ChatMessages = ({
  messages,
  liveText,
  running,
  projectId,
}: ChatMessagesProps) => {
  const { t } = useTranslation("agentChat");
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedToBottomRef = useRef(true);
  const documentsQuery = useDocuments(projectId);
  const docIndex = useMemo(
    () => buildDocRefIndex(documentsQuery.data ?? []),
    [documentsQuery.data],
  );

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    pinnedToBottomRef.current = distanceFromBottom <= BOTTOM_STICK_THRESHOLD_PX;
  };

  // Only follow new output (tokens, messages) when the user is parked at the
  // bottom. Use an instant jump, not smooth: smooth scrolling fires its own
  // intermediate scroll events that would race the pinned-state detection.
  useEffect(() => {
    if (!pinnedToBottomRef.current) return;
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, liveText]);

  const visible = messages.filter((m) => m.role !== "summary");

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="flex flex-col"
      style={{
        gap: 12,
        padding: 12,
        overflowY: "auto",
        flex: 1,
        minWidth: 0,
      }}
    >
      {visible.length === 0 && !liveText && (
        <div
          className="dim"
          style={{ fontSize: 12, textAlign: "center", marginTop: 24 }}
        >
          {t("messages.emptyHint")}
        </div>
      )}
      {visible.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          projectId={projectId}
          index={docIndex}
        />
      ))}
      {liveText && (
        <Bubble role="assistant">
          <Markdown
            text={stripToolCallNoise(liveText)}
            projectId={projectId}
            index={docIndex}
          />
        </Bubble>
      )}
      {running && !liveText && (
        <div className="dim mono" style={{ fontSize: 11 }}>
          {t("messages.thinking")}
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
};

const MessageBubble = ({
  message,
  projectId,
  index,
}: {
  message: ChatMessage;
  projectId: string;
  index: DocRefIndex;
}) => {
  if (message.role === "tool") {
    return (
      <>
        {message.blocks.map((block, i) => (
          <ToolResultBlock key={i} block={block} />
        ))}
      </>
    );
  }
  return (
    <Bubble role={message.role}>
      {message.blocks.map((block, i) => (
        <BlockView
          key={i}
          block={block}
          projectId={projectId}
          index={index}
          sanitize={message.role === "assistant"}
        />
      ))}
    </Bubble>
  );
};

const BlockView = ({
  block,
  projectId,
  index,
  sanitize,
}: {
  block: ChatContentBlock;
  projectId: string;
  index: DocRefIndex;
  sanitize: boolean;
}) => {
  if (block.kind === "text" && block.text) {
    const text = sanitize ? stripToolCallNoise(block.text) : block.text;
    if (!text) return null;
    return <Markdown text={text} projectId={projectId} index={index} />;
  }
  if (block.kind === "tool_call") {
    const docId =
      typeof block.args.doc_id === "string" ? block.args.doc_id : null;
    return (
      <div
        className="mono"
        style={{
          fontSize: 11,
          color: "var(--fg-2)",
          display: "flex",
          gap: 6,
          alignItems: "center",
          flexWrap: "wrap",
          minWidth: 0,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
        }}
      >
        <Wrench size={11} style={{ flexShrink: 0 }} />
        <span style={{ minWidth: 0 }}>{block.tool_name}</span>
        {docId && <DocChip projectId={projectId} docId={docId} />}
        <span className="dim" style={{ minWidth: 0 }}>
          ({JSON.stringify(block.args)})
        </span>
      </div>
    );
  }
  return null;
};

const ToolResultBlock = ({ block }: { block: ChatContentBlock }) => {
  const { t } = useTranslation("agentChat");
  const [open, setOpen] = useState(false);
  if (block.kind !== "tool_result") return null;
  // First non-empty line of the output — a peek at the result without expanding.
  const preview =
    (block.result ?? "")
      .split("\n")
      .map((line) => line.trim())
      .find((line) => line.length > 0) ?? "";
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 6,
        background: "var(--bg-1)",
        fontSize: 11.5,
        minWidth: 0,
        maxWidth: "100%",
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        className="flex items-center"
        style={{
          gap: 6,
          padding: "6px 10px",
          width: "100%",
          color: block.is_error ? "var(--c-err)" : "var(--fg-2)",
        }}
        onClick={() => {
          setOpen((v) => !v);
        }}
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Wrench size={11} style={{ flexShrink: 0 }} />
        <span className="mono" style={{ flexShrink: 0 }}>
          {block.tool_name}
        </span>
        <span className="dim" style={{ flexShrink: 0 }}>
          {block.is_error ? t("messages.toolError") : t("messages.toolResult")}
        </span>
        {!open && preview && (
          <span
            className="dim truncate"
            style={{ minWidth: 0, flex: 1, textAlign: "left" }}
          >
            {preview}
          </span>
        )}
      </button>
      {open && (
        <pre
          className="mono"
          style={{
            margin: 0,
            padding: "0 10px 8px 10px",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            overflowWrap: "anywhere",
          }}
        >
          {block.result}
        </pre>
      )}
    </div>
  );
};

const Bubble = ({
  role,
  children,
}: {
  role: string;
  children: React.ReactNode;
}) => {
  const { t } = useTranslation("agentChat");
  const isUser = role === "user";
  const roleKey = ROLE_LABEL_KEY[role];
  return (
    <div
      className="flex flex-col"
      style={{ gap: 3, alignItems: isUser ? "flex-end" : "flex-start" }}
    >
      <span
        className="dim"
        style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}
      >
        {roleKey ? t(roleKey) : role}
      </span>
      <div
        style={{
          maxWidth: "92%",
          minWidth: 0,
          padding: "8px 11px",
          borderRadius: 8,
          fontSize: 12.5,
          lineHeight: 1.5,
          background: isUser
            ? "var(--accent-soft, var(--bg-2))"
            : "var(--bg-1)",
          border: "1px solid var(--border)",
          overflow: "hidden",
        }}
      >
        {children}
      </div>
    </div>
  );
};

const DocChip = ({
  projectId,
  docId,
}: {
  projectId: string;
  docId: string;
}) => {
  const navigate = useNavigate();
  const target = docHrefForId(projectId, docId);
  return (
    <a
      href={target}
      className="doc-ref"
      onClick={(event) => {
        event.preventDefault();
        void navigate(target);
      }}
    >
      {docId}
    </a>
  );
};

const Markdown = ({
  text,
  projectId,
  index,
}: {
  text: string;
  projectId: string;
  index: DocRefIndex;
}) => {
  const navigate = useNavigate();
  const remarkPlugins = useMemo(
    () => [remarkGfm, remarkDocLinks(index)] as Options["remarkPlugins"],
    [index],
  );
  const urlTransform = useMemo<UrlTransform>(
    () => (url) => (isDocHref(url) ? url : defaultUrlTransform(url)),
    [],
  );
  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        if (isDocHref(href)) {
          const target = docHrefForId(projectId, docIdFromHref(href));
          return (
            <a
              href={target}
              className="doc-ref"
              onClick={(event) => {
                event.preventDefault();
                void navigate(target);
              }}
            >
              {children}
            </a>
          );
        }
        return (
          <a href={href} target="_blank" rel="noreferrer noopener">
            {children}
          </a>
        );
      },
    }),
    [navigate, projectId],
  );
  return (
    <div className="chat-md">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        urlTransform={urlTransform}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
};
