import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";

const SyncTexBoxSchema = z.object({
  page: z.number(),
  x: z.number(),
  y: z.number(),
  width: z.number(),
  height: z.number(),
});

const SyncTexForwardSchema = z.object({ boxes: z.array(SyncTexBoxSchema) });

const SyncTexInverseSchema = z.object({
  file: z.string(),
  line: z.number(),
  column: z.number(),
});

export type SyncTexBox = z.infer<typeof SyncTexBoxSchema>;
export type SyncTexInverse = z.infer<typeof SyncTexInverseSchema>;

export const synctexApi = {
  /** Source (file, line) -> PDF boxes (page + position in PDF points). */
  forward: (projectId: string, docId: string, file: string, line: number) =>
    apiClient
      .get(
        `/projects/${projectId}/documents/${docId}/synctex/forward` +
          `?file=${encodeURIComponent(file)}&line=${String(line)}`,
      )
      .then(parseResp(SyncTexForwardSchema)),

  /** PDF (page, x, y in points from top-left) -> source (file, line, column). */
  inverse: (
    projectId: string,
    docId: string,
    page: number,
    x: number,
    y: number,
  ) =>
    apiClient
      .get(
        `/projects/${projectId}/documents/${docId}/synctex/inverse` +
          `?page=${String(page)}&x=${String(x)}&y=${String(y)}`,
      )
      .then(parseResp(SyncTexInverseSchema)),
};
