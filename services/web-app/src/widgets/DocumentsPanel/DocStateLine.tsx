import { useTranslation } from "react-i18next";
import {
  buildStateOf,
  formatElapsed,
  silentMinutes,
  useCompileSlot,
  useNowWhile,
  type BuildState,
} from "@entities/compile";
import type { DocStatus } from "@entities/document";

type Tone = "neutral" | "info" | "warn" | "err" | "ok";

const TONE_COLOR: Record<Tone, string> = {
  neutral: "var(--fg-3)",
  info: "var(--c-info)",
  warn: "var(--c-warn)",
  err: "var(--c-err)",
  ok: "var(--c-ok)",
};

export type DocStateLineProps = {
  projectId: string;
  docId: string;
  status: DocStatus;
};

/**
 * Подпись состояния сборки документа: «в очереди», «собирается 1:05», «не отвечает 6 мин»,
 * «ошибка», «собран». Красным горит только запущенная раннером и замолчавшая сборка.
 */
export const DocStateLine = ({
  projectId,
  docId,
  status,
}: DocStateLineProps) => {
  const { t } = useTranslation("workbench");
  const slot = useCompileSlot(projectId, docId);
  const live = slot?.status === "running";
  const now = useNowWhile(live);
  const state: BuildState = buildStateOf(slot, now);
  let text: string | null = null;
  let tone: Tone = "neutral";
  switch (state.kind) {
    case "queued": {
      if (state.noRunner) {
        text = t("documents.state.noRunner");
        tone = "warn";
      } else if (state.personal) {
        text = t("documents.state.personal");
      } else if (state.retry !== null) {
        text = t("documents.state.retry", state.retry);
        tone = "warn";
      } else if (state.busy !== null && state.capacity !== null) {
        const params = {
          busy: state.busy,
          capacity: state.capacity,
          position: state.position ?? 0,
        };
        text =
          state.position === null
            ? t("documents.state.queuedBusy", params)
            : t("documents.state.queuedBusyPos", params);
      } else {
        text =
          state.position === null
            ? t("documents.state.queued")
            : t("documents.state.queuedPos", { position: state.position });
      }
      break;
    }
    case "starting":
      text = t("documents.state.starting");
      break;
    case "running":
      text = t("documents.state.running", {
        time: formatElapsed(state.elapsedMs),
      });
      tone = "info";
      break;
    case "silent":
      text = t("documents.state.silent", {
        count: silentMinutes(state.silentMs),
      });
      tone = "err";
      break;
    case "idle":
      if (status === "err") {
        text = t("documents.state.failed");
        tone = "err";
      } else if (status === "ok" || status === "warn") {
        text = t("documents.state.built");
        tone = "ok";
      }
      break;
  }
  if (text === null) return null;
  return (
    <span
      data-testid={`doc-state-${docId}`}
      data-state={state.kind === "idle" ? status : state.kind}
      style={{
        fontSize: "0.65625rem",
        lineHeight: 1.3,
        color: TONE_COLOR[tone],
      }}
    >
      {text}
    </span>
  );
};
