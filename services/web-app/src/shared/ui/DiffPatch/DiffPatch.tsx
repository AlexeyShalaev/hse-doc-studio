import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { type DiffStat, changeMeta, parsePatch } from "./diffPatch.model";

// Renders one file's unified diff as numbered, colour-coded lines with a sticky
// header (status + path + ±counts). Presentational: the caller supplies the
// patch text and the pre-computed ±counts.

export type DiffPatchFile = {
  path: string;
  /** Git status letter: A, M, D, R, C. Anything else renders neutral. */
  change: string;
  patch: string;
  binary: boolean;
};

export type DiffPatchProps = {
  file: DiffPatchFile;
  stat: DiffStat;
  maxHeight?: number;
};

const sign = (kind: string): string =>
  kind === "add" ? "+" : kind === "del" ? "−" : " ";

export const DiffPatch = ({ file, stat, maxHeight = 460 }: DiffPatchProps) => {
  const { t } = useTranslation("uiPrimitives");
  const meta = changeMeta(file.change);
  const hunks = useMemo(
    () => (file.binary ? [] : parsePatch(file.patch)),
    [file.binary, file.patch],
  );

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {/* sticky file header */}
      <div
        className="flex items-center"
        style={{
          gap: "0.5rem",
          padding: "0.5rem 0.75rem",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <span
          className="mono"
          style={{
            flexShrink: 0,
            width: "1rem",
            textAlign: "center",
            fontSize: "0.6875rem",
            fontWeight: 700,
            color: meta.color,
          }}
          title={meta.label}
        >
          {meta.letter}
        </span>
        <span
          className="mono truncate"
          style={{ fontSize: "0.71875rem", flex: 1, color: "var(--fg-0)" }}
          title={file.path}
        >
          {file.path}
        </span>
        {!file.binary && (
          <span
            className="mono"
            style={{
              fontSize: "0.65625rem",
              flexShrink: 0,
              display: "flex",
              gap: "0.375rem",
            }}
          >
            <span style={{ color: "var(--c-ok)" }}>+{String(stat.add)}</span>
            <span style={{ color: "var(--c-err)" }}>−{String(stat.del)}</span>
          </span>
        )}
      </div>

      {file.binary ? (
        <div
          className="dim"
          style={{ padding: "0.75rem", fontSize: "0.71875rem" }}
        >
          {t("diffPatch.binary")}
        </div>
      ) : hunks.length === 0 ? (
        <div
          className="dim"
          style={{ padding: "0.75rem", fontSize: "0.71875rem" }}
        >
          {t("diffPatch.noTextChanges")}
        </div>
      ) : (
        <div className="vcs-diff" style={{ maxHeight, overflow: "auto" }}>
          {hunks.map((hunk, hi) => (
            <div key={hi}>
              <div className="vcs-diff-hunk">{hunk.header}</div>
              {hunk.lines.map((line, li) => (
                <div key={li} className="vcs-diff-line" data-kind={line.kind}>
                  <span className="vcs-diff-gutter">{line.oldNo ?? ""}</span>
                  <span className="vcs-diff-gutter">{line.newNo ?? ""}</span>
                  <span className="vcs-diff-sign">{sign(line.kind)}</span>
                  <span className="vcs-diff-code">{line.text || " "}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

DiffPatch.displayName = "DiffPatch";
