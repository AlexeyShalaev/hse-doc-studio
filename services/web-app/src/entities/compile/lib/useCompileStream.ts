import { useEffect } from "react";
import { createSSEStream } from "@shared/lib/sse";
import { compileApi } from "../api/compileApi";

type LogData = { line: string; ts: string };
type DoneData = {
  status: "success" | "failure" | "cancelled";
  pages: number | null;
  warnings: number;
  errors: number;
};
type StreamEventData = LogData | DoneData;

export const useCompileStream = (
  projectId: string,
  docId: string,
  compileId: string | null,
  onLog: (line: string) => void,
  onDone: (status: "success" | "failure" | "cancelled") => void,
) => {
  useEffect(() => {
    if (!compileId) return;

    const url = compileApi.streamUrl(projectId, docId, compileId);
    const cleanup = createSSEStream<StreamEventData>(url, (event) => {
      if (event.type === "log") {
        const data = event.data as LogData;
        onLog(data.line);
      }
      if (event.type === "done") {
        const data = event.data as DoneData;
        onDone(data.status);
      }
    });

    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compileId, projectId, docId]);
};
