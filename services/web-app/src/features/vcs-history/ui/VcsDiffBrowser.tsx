import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileDiff } from "lucide-react";
import { Spinner } from "@shared/ui/Spinner";
import type { VcsDiff } from "@entities/vcs";
import { type DiffStat, countChanges } from "./vcsDiff.model";
import { VcsChangedFiles } from "./VcsChangedFiles";
import { VcsFilePatch } from "./VcsFilePatch";

// Git-style diff browser: a summary bar, a searchable file tree/list, and the
// selected file's diff (master-detail) — instead of stacking every file's patch
// down the page. Replaces the old VcsDiffView.

export type VcsDiffBrowserProps = {
  diff: VcsDiff | undefined;
  isLoading: boolean;
  emptyHint?: string;
};

export const VcsDiffBrowser = ({
  diff,
  isLoading,
  emptyHint,
}: VcsDiffBrowserProps) => {
  const { t } = useTranslation("vcsHistory");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const files = useMemo(() => diff?.files ?? [], [diff]);

  const stats = useMemo(() => {
    const map = new Map<string, DiffStat>();
    for (const f of files) {
      map.set(f.path, f.binary ? { add: 0, del: 0 } : countChanges(f.patch));
    }
    return map;
  }, [files]);

  const totals = useMemo(() => {
    let add = 0;
    let del = 0;
    stats.forEach((s) => {
      add += s.add;
      del += s.del;
    });
    return { add, del };
  }, [stats]);

  if (isLoading) {
    return (
      <div className="flex justify-center" style={{ padding: 24 }}>
        <Spinner size="sm" />
      </div>
    );
  }

  if (!diff || files.length === 0) {
    return (
      <div
        className="dim flex items-center justify-center"
        style={{ gap: 8, padding: 28, fontSize: 12 }}
      >
        <FileDiff size={14} />
        {emptyHint ?? t("diffBrowser.emptyHint")}
      </div>
    );
  }

  // Derive the active file (no effect needed): keep the user's pick if it's
  // still present, otherwise fall back to the first file.
  const activePath = files.some((f) => f.path === selectedPath)
    ? selectedPath
    : (files[0]?.path ?? null);
  const activeFile = files.find((f) => f.path === activePath) ?? null;

  const multiFile = files.length > 1;

  return (
    <div className="vcs-diff-browser flex flex-col" style={{ gap: 10 }}>
      {/* summary */}
      <div
        className="flex items-center"
        style={{ gap: 10, flexWrap: "wrap", fontSize: 11.5 }}
      >
        <span className="dim">
          {t("diffBrowser.filesChanged", { count: files.length })}
        </span>
        <span className="mono" style={{ color: "var(--c-ok)" }}>
          +{String(totals.add)}
        </span>
        <span className="mono" style={{ color: "var(--c-err)" }}>
          −{String(totals.del)}
        </span>
        {diff.truncated && (
          <span className="dim">{t("diffBrowser.truncated")}</span>
        )}
      </div>

      {/* master-detail: file list on the left, patch on the right. Collapses
          to one column on a narrow container (see .vcs-diff-master CSS). */}
      <div className={multiFile ? "vcs-diff-master" : undefined}>
        {multiFile && (
          <VcsChangedFiles
            files={files}
            stats={stats}
            activePath={activePath}
            onSelect={setSelectedPath}
            maxHeight={540}
          />
        )}
        {activeFile && (
          <VcsFilePatch
            key={activeFile.path}
            file={activeFile}
            stat={stats.get(activeFile.path) ?? { add: 0, del: 0 }}
            maxHeight={540}
          />
        )}
      </div>
    </div>
  );
};
