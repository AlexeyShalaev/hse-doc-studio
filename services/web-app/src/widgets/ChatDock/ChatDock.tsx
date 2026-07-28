import { useTranslation } from "react-i18next";
import { SystemChatPanel } from "@features/agent-chat";
import { usePaneResize } from "@shared/lib";
import { ResizeHandle } from "@shared/ui";

// One shared width for the docked agent everywhere it appears (Welcome, the
// project wizard, a project workspace), so resizing it on one screen carries
// over to the others.
const CHAT_WIDTH_STORAGE_KEY = "hse-studio.workspace.chatWidth";
const CHAT_WIDTH = { default: 400, min: 320, max: 720 };

export type ChatDockProps = {
  // Bound project (if any). New chats started here gain its tools + context;
  // omit it outside a project for the app/system agent.
  projectId?: string;
  onClose: () => void;
};

// The one unified agent docked into a page layout: a left drag handle plus the
// panel, right-aligned, pushing content rather than overlaying it. Render it as
// a sibling inside a horizontal flex row between the title and status bars.
export const ChatDock = ({ projectId, onClose }: ChatDockProps) => {
  const { t } = useTranslation("appChrome");
  const resize = usePaneResize({
    storageKey: CHAT_WIDTH_STORAGE_KEY,
    defaultWidth: CHAT_WIDTH.default,
    minWidth: CHAT_WIDTH.min,
    maxWidth: CHAT_WIDTH.max,
    direction: -1,
  });

  return (
    <div className="chat-dock">
      <ResizeHandle
        active={resize.isResizing}
        label={t("chatDock.resizeHint")}
        onDoubleClick={resize.reset}
        onKeyNudge={resize.nudge}
        onPointerDown={resize.startResize}
      />
      <SystemChatPanel
        {...(projectId ? { projectId } : {})}
        width={resize.width}
        onClose={onClose}
      />
    </div>
  );
};
