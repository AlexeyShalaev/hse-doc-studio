import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { Info } from "lucide-react";
import {
  getDocMeta,
  useCheckResults,
  useCheckRules,
  useDocChecksActions,
  useDocument,
} from "@entities/document";
import { useProject } from "@entities/project";
import { buildFixFindingPrompt, RulesView } from "@entities/checks";
import { useIgnoreFinding } from "@features/source-edit";
import type { CheckRuleResponse } from "@shared/api/types";
import { pickLocalized, toPosixPath, useWorkspaceStore } from "@shared/lib";
import { ChecksToolbar } from "./ChecksToolbar";
import { ResultsView } from "./ResultsView";
import type { CheckItem, FilterKind, Mode, SeverityCounts } from "./types";

export type ChecksPaneProps = {
  projectId: string;
  docId: string;
};

export const ChecksPane = ({ projectId, docId }: ChecksPaneProps) => {
  const { t, i18n } = useTranslation("documents");
  // Scope to this document: only findings in its own file or files it imports,
  // not every finding in the project.
  const { data: results } = useCheckResults(projectId, docId, "document");
  const { data: rulesData } = useCheckRules(projectId, docId);
  const { data: project } = useProject(projectId);
  const { data: doc } = useDocument(projectId, docId);
  const askAgent = useWorkspaceStore((state) => state.askAgent);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // Pass the doc so docMeta.file matches the API path (team layouts prefix the
  // author base) — the main-file comparison below depends on it.
  const docMeta = getDocMeta(docId, doc);
  const [filter, setFilter] = useState<FilterKind>("all");
  const [mode, setMode] = useState<Mode>("results");

  const {
    currentOverride,
    updateOverride,
    toggleRule,
    setSeverity,
    resetSeverity,
    severityOverride,
    isPending: isMutating,
  } = useDocChecksActions(projectId, docId);

  // Jump from a finding into the editor at its line. Findings in the document's
  // main .tex open the editable «Исходник» tab; findings in other files
  // (common/*, \input children) open the «Файлы проекта» panel on that file.
  const handleGoToSource = (item: CheckItem) => {
    if (item.line == null) return;
    const file = item.file != null ? toPosixPath(item.file) : null;
    if (file == null || file === toPosixPath(docMeta.file)) {
      const params = new URLSearchParams(searchParams);
      params.set("tab", "source");
      params.set("line", String(item.line));
      setSearchParams(params, { replace: true });
      return;
    }
    const search = new URLSearchParams({ file, line: String(item.line) });
    void navigate(`/projects/${projectId}/files?${search.toString()}`);
  };

  const disabledRules = useMemo(
    () => new Set(currentOverride.disabled),
    [currentOverride.disabled],
  );
  const disabledCategories = useMemo(
    () => new Set(currentOverride.disabled_categories),
    [currentOverride.disabled_categories],
  );

  // Maintain `disabled` and `enabled` as symmetric lists. This handles the
  // tricky case where a rule's category is in `disabled_categories`: turning
  // the rule back on must add it to `enabled` (force-enable), not just remove
  // from `disabled`. Otherwise the user's click does nothing.
  const handleToggleRule = (ruleId: string, currentlyEnabled: boolean) => {
    if (currentlyEnabled) {
      updateOverride({
        disabled: [...currentOverride.disabled, ruleId],
        enabled: currentOverride.enabled.filter((id) => id !== ruleId),
      });
    } else {
      updateOverride({
        disabled: currentOverride.disabled.filter((id) => id !== ruleId),
        enabled: [...new Set([...currentOverride.enabled, ruleId])],
      });
    }
  };

  const handleToggleCategory = (category: string) => {
    const next = disabledCategories.has(category)
      ? currentOverride.disabled_categories.filter((c) => c !== category)
      : [...currentOverride.disabled_categories, category];
    updateOverride({ disabled_categories: next });
  };

  // Bulk: if any rule in the group is enabled, turn them all off; otherwise
  // turn them all on. Symmetric maintenance of disabled/enabled, same logic
  // as handleToggleRule but across the whole group.
  const handleToggleSource = (
    ruleIds: readonly string[],
    anyEnabled: boolean,
  ) => {
    const idSet = new Set(ruleIds);
    if (anyEnabled) {
      updateOverride({
        disabled: [...new Set([...currentOverride.disabled, ...ruleIds])],
        enabled: currentOverride.enabled.filter((id) => !idSet.has(id)),
      });
    } else {
      updateOverride({
        disabled: currentOverride.disabled.filter((id) => !idSet.has(id)),
        enabled: [...new Set([...currentOverride.enabled, ...ruleIds])],
      });
    }
  };

  const rulesBySource = useMemo<
    readonly (readonly [string, readonly CheckRuleResponse[]])[]
  >(() => {
    const grouped = new Map<string, CheckRuleResponse[]>();
    for (const r of rulesData ?? []) {
      const list = grouped.get(r.source) ?? [];
      list.push(r);
      grouped.set(r.source, list);
    }
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rulesData]);

  const categoriesWithCounts = useMemo<
    readonly (readonly [string, number])[]
  >(() => {
    const counts = new Map<string, number>();
    for (const r of rulesData ?? []) {
      if (r.category) {
        counts.set(r.category, (counts.get(r.category) ?? 0) + 1);
      }
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rulesData]);

  const totalRules = rulesData?.length ?? 0;
  const enabledCount = (rulesData ?? []).filter((r) => r.enabled).length;

  // Project folder is the base for resolving relative paths in check results
  // (CheckResult.location.file is relative to the project root).
  const projectFolder = project?.folder ?? "";

  // Results-mode derived data.
  const findingItems: readonly CheckItem[] = (results?.results ?? []).map(
    (r, i): CheckItem => {
      const isSkipped = r.status === "skipped_custom";
      const base: CheckItem = {
        id: `${r.rule_id}-${String(i)}`,
        // Apply the severity override optimistically so a change reflects
        // instantly (and for any rule id), without a backend re-resolve.
        // A skipped_custom result overrides any severity — it's a neutral
        // state, not something the user's severity override should color.
        sev: isSkipped
          ? "skipped"
          : (severityOverride[r.rule_id] ?? r.severity),
        title: r.message,
        body: r.message,
        ref: r.rule_id,
      };
      if (isSkipped && r.skip_reason) base.skippedReason = r.skip_reason;
      const withLine =
        r.location?.line != null ? { ...base, line: r.location.line } : base;
      const file = r.location?.file;
      if (file) {
        const withFile: CheckItem = { ...withLine, file };
        if (projectFolder) withFile.absolutePath = `${projectFolder}/${file}`;
        return withFile;
      }
      return withLine;
    },
  );

  // Passed (OK) rules: enabled rules that produced no findings in the last
  // run. Shown so the student sees which requirements are already satisfied,
  // not only the violations. Built only after a real check run (compile_id
  // present or findings exist) — a never-built document must not claim that
  // every rule passes.
  const hasRun =
    (results?.compile_id ?? null) != null || findingItems.length > 0;
  const failingIds = useMemo(
    () => new Set((results?.results ?? []).map((r) => r.rule_id)),
    [results],
  );
  // LanguageTool findings arrive under synthetic `lt:<RULE>` ids — they
  // belong to the `language`-category gate rule, which must not read as OK.
  const hasLtFindings = [...failingIds].some((id) => id.startsWith("lt:"));
  const okItems: readonly CheckItem[] = hasRun
    ? (rulesData ?? [])
        .filter(
          (r) =>
            r.enabled &&
            !failingIds.has(r.rule_id) &&
            !(hasLtFindings && r.category === "language"),
        )
        .map(
          (r): CheckItem => ({
            id: `ok-${r.rule_id}`,
            sev: "ok",
            title: pickLocalized(r.title, i18n.language, r.rule_id),
            body: "",
            ref: r.rule_id,
          }),
        )
    : [];

  // Issues first, satisfied rules after them.
  const checks: readonly CheckItem[] = [...findingItems, ...okItems];

  const counts: SeverityCounts = {
    all: checks.length,
    ok: checks.filter((c) => c.sev === "ok").length,
    warn: checks.filter((c) => c.sev === "warn").length,
    err: checks.filter((c) => c.sev === "err").length,
    info: checks.filter((c) => c.sev === "info").length,
    skipped: checks.filter((c) => c.sev === "skipped").length,
  };
  const filtered =
    filter === "all" ? checks : checks.filter((c) => c.sev === filter);
  // Skipped rules don't participate in pass/fail accounting — they weren't
  // run at all, so counting them against compliance would misleadingly drag
  // the rate down for a custom document.
  const gradedCount = checks.length - counts.skipped;
  const passRate =
    gradedCount > 0 ? Math.round((counts.ok / gradedCount) * 100) : 0;

  const findingLocation = (item: CheckItem): string =>
    item.file
      ? t("checks.findingLocation", {
          path: `${item.file}${item.line != null ? `:${String(item.line)}` : ""}`,
        })
      : "";

  const handleFixWithAi = (item: CheckItem) => {
    askAgent(
      buildFixFindingPrompt({
        docCode: docMeta.code,
        docId,
        ruleId: item.ref,
        message: item.body,
        file: item.file,
        line: item.line,
      }),
    );
  };

  // Suppress one occurrence (not the whole rule) by writing a `% hse-noqa`
  // comment onto its source line — the same per-finding ignore offered inline
  // in the editor, available here without opening the file.
  const ignoreFinding = useIgnoreFinding(projectId, docId);
  const handleIgnoreFinding = (item: CheckItem) => {
    if (item.file == null || item.line == null) return;
    ignoreFinding.mutate({
      file: item.file,
      line: item.line,
      ruleId: item.ref,
    });
  };

  const handleFixAll = () => {
    // Skipped items have no source to fix (that's why they were skipped) —
    // excluded from the bulk agent prompt same as passed ("ok") items.
    const issues = filtered.filter(
      (c) => c.sev !== "ok" && c.sev !== "skipped",
    );
    if (issues.length === 0) return;
    const MAX_LISTED = 25;
    const lines = issues
      .slice(0, MAX_LISTED)
      .map(
        (c) =>
          `- [${c.sev.toUpperCase()}] ${c.ref}: ${c.body}${findingLocation(c)}`,
      );
    const more =
      issues.length > MAX_LISTED
        ? t("checks.fixAllMore", { count: issues.length - MAX_LISTED })
        : "";
    askAgent(
      t("checks.fixAllPrompt", {
        code: docMeta.code,
        docId,
        list: lines.join("\n"),
        more,
      }),
    );
  };

  return (
    <div className="flex flex-col" style={{ flex: 1, minHeight: 0 }}>
      {doc?.custom_file != null && (
        <div
          className="flex items-center gap-2"
          style={{
            padding: "10px 18px",
            borderBottom: "1px solid var(--border)",
            background: "var(--c-info-soft)",
            fontSize: 11.5,
            color: "var(--fg-1)",
          }}
        >
          <Info size={13} style={{ color: "var(--c-info)", flexShrink: 0 }} />
          <span>{t("checks.customFileBanner")}</span>
        </div>
      )}
      <ChecksToolbar
        mode={mode}
        onModeChange={setMode}
        filter={filter}
        onFilterChange={setFilter}
        counts={counts}
        passRate={passRate}
        onFixAll={handleFixAll}
        totalRules={totalRules}
        enabledCount={enabledCount}
      />
      {mode === "results" ? (
        <ResultsView
          filtered={filtered}
          disabledRules={disabledRules}
          onToggleRule={toggleRule}
          isMutating={isMutating}
          severityOverride={severityOverride}
          onSetSeverity={setSeverity}
          onResetSeverity={resetSeverity}
          onFixWithAi={handleFixWithAi}
          onIgnoreFinding={handleIgnoreFinding}
          isIgnoringFinding={ignoreFinding.isPending}
          onGoToSource={handleGoToSource}
        />
      ) : (
        <RulesView
          rulesBySource={rulesBySource}
          categoriesWithCounts={categoriesWithCounts}
          disabledCategories={disabledCategories}
          severityOverride={severityOverride}
          isMutating={isMutating}
          onToggleCategory={handleToggleCategory}
          onToggleSource={handleToggleSource}
          onToggleRule={handleToggleRule}
          onSetSeverity={setSeverity}
          onResetSeverity={resetSeverity}
        />
      )}
    </div>
  );
};
