import { useCallback } from "react";
import { useQueries } from "@tanstack/react-query";
import type { z } from "zod";
import {
  documentApi,
  documentKeys,
  useDocuments,
  type CheckResultsResponseSchema,
} from "@entities/document";
import { toPosixPath } from "@shared/lib";
import type { EditorDiagnostic } from "@shared/ui";
import { resultToDiagnostic } from "./findingsToDiagnostics";

type CheckResults = z.infer<typeof CheckResultsResponseSchema>;

export type DiagnosticsByFile = Map<string, EditorDiagnostic[]>;

/**
 * Aggregates check findings across all of the project's documents into a
 * `location.file → diagnostics` map. Lets the file explorer surface findings
 * for ANY file (incl. \input children / common files), not just a document's
 * main .tex. Reuses the per-document check-result cache (same query keys).
 */
export const useProjectDiagnostics = (projectId: string): DiagnosticsByFile => {
  const { data: documents } = useDocuments(projectId);
  const docs = documents ?? [];

  const combine = useCallback(
    (results: { data: CheckResults | undefined }[]): DiagnosticsByFile => {
      const byFile: DiagnosticsByFile = new Map();
      for (const result of results) {
        for (const finding of result.data?.results ?? []) {
          const file = finding.location?.file;
          if (file == null) continue;
          const diagnostic = resultToDiagnostic(finding);
          if (!diagnostic) continue;
          const key = toPosixPath(file);
          const list = byFile.get(key);
          if (list) list.push(diagnostic);
          else byFile.set(key, [diagnostic]);
        }
      }
      return byFile;
    },
    [],
  );

  return useQueries({
    queries: docs.map((doc) => ({
      queryKey: documentKeys.checkResults(projectId, doc.id),
      queryFn: () => documentApi.getCheckResults(projectId, doc.id),
      enabled: !!projectId && !!doc.id,
    })),
    combine,
  });
};
