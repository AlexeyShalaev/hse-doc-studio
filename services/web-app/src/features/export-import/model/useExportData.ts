import { useMutation } from "@tanstack/react-query";
import { exportImportApi } from "../api/exportImportApi";
import type { ExportBundle, ExportRequest } from "../api/exportImportApi";

// Colons (from the ISO timestamp) are invalid in Windows filenames — strip the
// sub-second/timezone tail and swap separators for a clean, sortable stamp.
const buildFilename = (isoTimestamp: string): string => {
  const stamp = isoTimestamp.slice(0, 19).replace(/[:T]/g, "-");
  return `hse-studio-settings-${stamp || "export"}.json`;
};

const downloadBundle = (data: ExportBundle): void => {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = buildFilename(data.exported_at);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

export const useExportData = () =>
  useMutation<ExportBundle, Error, ExportRequest>({
    mutationFn: (request) => exportImportApi.exportData(request),
    onSuccess: downloadBundle,
  });
