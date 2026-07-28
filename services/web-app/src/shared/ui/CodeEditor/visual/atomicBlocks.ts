import { syntaxTree } from "@codemirror/language";
import {
  EditorState,
  RangeSet,
  StateField,
  type Range,
} from "@codemirror/state";
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view";
import type { SyntaxNode } from "@lezer/common";
import type { VisualEmbeddedInputKind } from "../types";
import { insideSelection, touchesSelection } from "./reveal";
import { externalDocumentSync, setPreambleCollapsed } from "./effects";
import { visualCallbacksFacet, visualConfigFacet } from "./config";
import {
  ALIGNMENT_ENVS,
  cardEnvironmentKind,
  FRAMED_ENVS,
  inputBasename,
  isEmbeddedInput,
  MATH_BLOCK_ENVS,
} from "./nodeSets";
import {
  BannerWidget,
  ChangeLogInputBlockWidget,
  CommentBlockWidget,
  EmbeddedInputBlockWidget,
  EnvironmentBlockWidget,
  FigureBlockWidget,
  HintCalloutWidget,
  MathWidget,
  PreambleCollapseWidget,
  PreambleWidget,
  RequirementsTableInputBlockWidget,
  TableBlockWidget,
  TitleInputBlockWidget,
} from "./widgets";

/**
 * Layer A of the visual mode: decorations that change the vertical layout
 * (block widgets, replaces spanning line breaks) — CodeMirror requires these
 * to come from a StateField, not a ViewPlugin. Covers:
 *  - the preamble collapsed into a banner (everything up to `\begin{document}`),
 *  - display math (`\[…\]`, `$$…$$`, equation/align environments) as KaTeX
 *    widgets,
 *  - lines holding only a list `\begin`/`\end` marker, removed entirely.
 *
 * A construct touched by the selection is "revealed": its decoration is
 * skipped so the raw LaTeX is visible and editable in place.
 */

export type BlockZone =
  | { kind: "preamble"; from: number; to: number; lineCount: number }
  | { kind: "math"; from: number; to: number; tex: string; block: boolean }
  | {
      kind: "hiddenLine";
      from: number;
      to: number;
      /** "end" = list end (Backspace merges into the last item);
       *  "envEnd" = highlighted-env end (reveal only, never merge). */
      marker: "begin" | "end" | "envEnd";
    }
  | { kind: "banner"; from: number; to: number }
  | { kind: "comments"; from: number; to: number; count: number }
  | { kind: "hint"; from: number; to: number; count: number; text: string }
  | { kind: "table"; from: number; to: number; source: string }
  | { kind: "figure"; from: number; to: number; source: string }
  | {
      kind: "environment";
      from: number;
      to: number;
      name: string;
      source: string;
    }
  | {
      kind: "embeddedInput";
      from: number;
      to: number;
      path: string;
      variant: VisualEmbeddedInputKind;
      source: string | undefined;
    };

const firstDescendant = (node: SyntaxNode, name: string): SyntaxNode | null => {
  let found: SyntaxNode | null = null;
  node.cursor().iterate((child) => {
    if (found) return false;
    if (child.name === name) {
      found = child.node;
      return false;
    }
    return undefined;
  });
  return found;
};

const inputPathNode = (node: SyntaxNode): SyntaxNode | null =>
  firstDescendant(node, "LiteralArgContent") ??
  firstDescendant(node, "SpaceDelimitedLiteralArgContent");

const inputConfigValue = <T>(
  values: Record<string, T> | undefined,
  path: string,
): T | undefined => {
  if (!values) return undefined;
  const normalized = path.replace(/\\/g, "/");
  return values[path] ?? values[normalized] ?? values[inputBasename(path)];
};

/** Pure tree walk → zone descriptors. Exported for unit tests. */
export const computeBlockZones = (state: EditorState): BlockZone[] => {
  const zones: BlockZone[] = [];
  const doc = state.doc;
  const tree = syntaxTree(state);
  const config = state.facet(visualConfigFacet);
  let preambleSeen = false;
  let preambleEnd = -1;
  /** Comment-only lines: line number → stripped text (for run grouping). */
  const commentLines = new Map<number, string>();

  const fullLineSpan = (
    from: number,
    to: number,
  ): { from: number; to: number } | null => {
    const first = doc.lineAt(from);
    const last = doc.lineAt(to);
    const before = doc.sliceString(first.from, from).trim();
    const after = doc.sliceString(to, last.to).trim();
    return before === "" && after === ""
      ? { from: first.from, to: last.to }
      : null;
  };

  // A line containing nothing but this marker node is removed together with
  // the preceding newline (so no blank line is left behind).
  const hiddenLineZone = (
    from: number,
    to: number,
    marker: "begin" | "end" | "envEnd",
  ): BlockZone | null => {
    const span = fullLineSpan(from, to);
    if (!span) return null;
    if (span.from > 0)
      return { kind: "hiddenLine", from: span.from - 1, to: span.to, marker };
    if (span.to < doc.length)
      return { kind: "hiddenLine", from: span.from, to: span.to + 1, marker };
    return null;
  };

  tree.iterate({
    enter: (node) => {
      if (node.name === "DocumentEnvironment" && !preambleSeen) {
        preambleSeen = true;
        const begin = node.node.getChild("BeginEnv");
        if (begin) {
          const beginLine = doc.lineAt(begin.from);
          preambleEnd = beginLine.to;
          zones.push({
            kind: "preamble",
            from: 0,
            to: beginLine.to,
            lineCount: beginLine.number,
          });
        }
        return;
      }

      // Full-line comments (nothing but whitespace before the `%`) collect
      // into runs collapsed below; trailing comments stay inline (Layer B).
      if (node.name === "Comment" && !config.showComments) {
        const line = doc.lineAt(node.from);
        if (doc.sliceString(line.from, node.from).trim() === "") {
          commentLines.set(
            line.number,
            line.text.replace(/^\s*%+\s?/, "").trimEnd(),
          );
        }
        return;
      }

      if (node.name === "ListEnvironment") {
        const list = node.node;
        for (const part of ["BeginEnv", "EndEnv"] as const) {
          const marker = list.getChild(part);
          if (marker) {
            const zone = hiddenLineZone(
              marker.from,
              marker.to,
              part === "BeginEnv" ? "begin" : "end",
            );
            if (zone) zones.push(zone);
          }
        }
        return;
      }

      // A host-declared full-line include (the HSE title/approval template) is
      // structural generated content, not an editable inline file link.
      if (
        node.name === "Input" ||
        node.name === "Include" ||
        node.name === "Subfile"
      ) {
        const pathNode = inputPathNode(node.node);
        if (!pathNode) return;
        const path = doc.sliceString(pathNode.from, pathNode.to);
        if (!isEmbeddedInput(path, config.embeddedInputBasenames)) return;
        const span = fullLineSpan(node.from, node.to);
        if (!span) return;
        const basename = inputBasename(path);
        zones.push({
          kind: "embeddedInput",
          from: span.from,
          to: span.to,
          path,
          variant:
            inputConfigValue(config.embeddedInputKinds, path) ??
            (basename === "change_log" ? "changeLog" : "generic"),
          source: inputConfigValue(config.embeddedInputSources, path),
        });
        return false;
      }

      // Environments. Configured «образец» blocks (e.g. hseExample) become a
      // banner + hidden end line with inline-editable content; structural or
      // code environments (table, figure, tikz, verbatim…) collapse into a
      // rich block card; prose environments fall through to Layer B framing.
      if (FRAMED_ENVS.has(node.name)) {
        const env = node.node;
        const begin = env.getChild("BeginEnv");
        // Specialized environments use per-kind name nodes (TabularEnvName,
        // TikzPictureEnvName…), so read the name straight from `\begin{…}`.
        const envName = begin
          ? (/\{\s*([^}]+?)\s*\}/.exec(
              doc.sliceString(begin.from, begin.to),
            )?.[1] ?? "")
          : "";

        if (
          node.name === "Environment" &&
          config.highlightEnvs.includes(envName)
        ) {
          const end = env.getChild("EndEnv");
          if (!begin || !end) return;
          const beginSpan = fullLineSpan(begin.from, begin.to);
          if (beginSpan) {
            zones.push({
              kind: "banner",
              from: beginSpan.from,
              to: beginSpan.to,
            });
          }
          const endZone = hiddenLineZone(end.from, end.to, "envEnd");
          if (endZone) zones.push(endZone);
          return;
        }

        const cardKind = cardEnvironmentKind(
          node.name,
          envName,
          config.highlightEnvs,
        );
        if (cardKind) {
          const span = fullLineSpan(node.from, node.to);
          if (span) {
            const source = doc.sliceString(span.from, span.to);
            zones.push(
              cardKind === "environment"
                ? {
                    kind: "environment",
                    from: span.from,
                    to: span.to,
                    name: envName,
                    source,
                  }
                : { kind: cardKind, from: span.from, to: span.to, source },
            );
            return false; // the card owns the whole subtree
          }
        }

        // Alignment environments (center/flushleft/flushright): hide the two
        // marker lines here; Layer B aligns the content, which stays editable.
        if (node.name === "Environment" && envName in ALIGNMENT_ENVS) {
          const end = env.getChild("EndEnv");
          if (begin) {
            const beginZone = hiddenLineZone(begin.from, begin.to, "begin");
            if (beginZone) zones.push(beginZone);
          }
          if (end) {
            const endZone = hiddenLineZone(end.from, end.to, "end");
            if (endZone) zones.push(endZone);
          }
          return;
        }

        return; // prose environment → Layer B keeps the raw frame
      }

      if (MATH_BLOCK_ENVS.has(node.name)) {
        if (!node.node.getChild("EndEnv")) return; // unterminated → leave raw
        const span = fullLineSpan(node.from, node.to);
        zones.push({
          kind: "math",
          from: span?.from ?? node.from,
          to: span?.to ?? node.to,
          // KaTeX renders {equation}/{align}… natively in display mode.
          tex: doc.sliceString(node.from, node.to),
          block: span != null,
        });
        return false;
      }

      if (node.name === "BracketMath") {
        if (!node.node.getChild("CloseBracketMath")) return;
        const math = node.node.getChild("Math");
        const span = fullLineSpan(node.from, node.to);
        zones.push({
          kind: "math",
          from: span?.from ?? node.from,
          to: span?.to ?? node.to,
          tex: math ? doc.sliceString(math.from, math.to) : "",
          block: span != null,
        });
        return false;
      }

      if (node.name === "DollarMath") {
        // Only `$$…$$` (a DisplayMath child) — inline `$…$` lives in Layer B.
        const display = node.node.getChild("DisplayMath");
        if (!display) return;
        if (doc.sliceString(node.to - 2, node.to) !== "$$") return; // unclosed
        const math = display.getChild("Math");
        const span = fullLineSpan(node.from, node.to);
        zones.push({
          kind: "math",
          from: span?.from ?? node.from,
          to: span?.to ?? node.to,
          tex: math ? doc.sliceString(math.from, math.to) : "",
          block: span != null,
        });
        return false;
      }

      return undefined;
    },
  });

  // Group consecutive comment-only lines into one collapsed zone. Comments
  // inside the preamble are skipped — the preamble banner already hides them
  // (nested block replaces would conflict). Runs starting with a configured
  // hint prefix («Подсказка: …») become readable callouts instead of chips.
  const numbers = [...commentLines.keys()].sort((a, b) => a - b);
  let runStart = -1;
  let previous = -2;
  const flushRun = (endLineNumber: number): void => {
    if (runStart < 0) return;
    const from = doc.line(runStart).from;
    if (from > preambleEnd) {
      const to = doc.line(endLineNumber).to;
      const count = endLineNumber - runStart + 1;
      const texts: string[] = [];
      for (let n = runStart; n <= endLineNumber; n += 1) {
        texts.push(commentLines.get(n) ?? "");
      }
      const first = texts[0] ?? "";
      const prefix = config.hintPrefixes.find((p) => first.startsWith(p));
      if (prefix !== undefined) {
        const text = texts
          .join(" ")
          .slice(prefix.length)
          .replace(/\s+/g, " ")
          .trim();
        zones.push({ kind: "hint", from, to, count, text });
      } else {
        zones.push({ kind: "comments", from, to, count });
      }
    }
    runStart = -1;
  };
  for (const n of numbers) {
    if (n !== previous + 1) {
      flushRun(previous);
      runStart = n;
    }
    previous = n;
  }
  flushRun(previous);

  return zones.sort((a, b) => a.from - b.from || a.to - b.to);
};

/**
 * Preamble reveal is strict-interior (the initial cursor at position 0 only
 * touches the zone and must not auto-expand it); everything else reveals on
 * boundary contact so arrow keys can walk into a widget.
 */
const zoneRevealed = (state: EditorState, zone: BlockZone): boolean =>
  zone.kind === "embeddedInput"
    ? false
    : zone.kind === "preamble"
      ? insideSelection(state.selection, zone.from, zone.to)
      : touchesSelection(state.selection, zone.from, zone.to);

/** Indices of zones currently revealed by the selection — the rebuild key. */
const revealKey = (state: EditorState, zones: BlockZone[]): string => {
  let key = "";
  zones.forEach((zone, index) => {
    if (zoneRevealed(state, zone)) key += String(index) + ",";
  });
  return key;
};

type Materialized = { deco: DecorationSet; atomics: DecorationSet };

/** Zones + selection + collapse flag → decoration sets. Exported for tests. */
export const materializeBlockZones = (
  state: EditorState,
  zones: BlockZone[],
  collapsed: boolean,
): Materialized => {
  const deco: Range<Decoration>[] = [];
  const atomics: Range<Decoration>[] = [];
  const callbacks = state.facet(visualCallbacksFacet);
  const config = state.facet(visualConfigFacet);

  for (const zone of zones) {
    const revealed = zoneRevealed(state, zone);
    if (zone.kind === "preamble") {
      if (collapsed && !revealed) {
        const replace = Decoration.replace({
          widget: new PreambleWidget(zone.lineCount),
          block: true,
        });
        deco.push(replace.range(zone.from, zone.to));
        atomics.push(replace.range(zone.from, zone.to));
      } else {
        deco.push(
          Decoration.widget({
            widget: new PreambleCollapseWidget(),
            side: -1,
            block: true,
          }).range(0),
        );
      }
    } else if (zone.kind === "embeddedInput") {
      const widget =
        zone.variant === "changeLog"
          ? new ChangeLogInputBlockWidget(
              zone.path,
              zone.source,
              config.macros.doccode,
              callbacks.onOpenFile,
            )
          : zone.variant === "titlePages" || zone.variant === "vkrTitle"
            ? new TitleInputBlockWidget(
                zone.path,
                zone.source,
                zone.variant,
                config.macros,
                callbacks.onOpenFile,
              )
            : zone.variant === "requirementsTable"
              ? new RequirementsTableInputBlockWidget(
                  zone.path,
                  zone.source,
                  callbacks.onOpenFile,
                )
              : new EmbeddedInputBlockWidget(
                  zone.path,
                  zone.source,
                  callbacks.onOpenFile,
                );
      const replace = Decoration.replace({
        widget,
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "math") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new MathWidget(zone.tex, true),
        block: zone.block,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "comments") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new CommentBlockWidget(zone.count),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "hint") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new HintCalloutWidget(zone.text),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "banner") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new BannerWidget(),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "table") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new TableBlockWidget(zone.source, callbacks.onEditTable),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "figure") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new FigureBlockWidget(zone.source, callbacks.resolveAssetUrl),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else if (zone.kind === "environment") {
      if (revealed) continue;
      const replace = Decoration.replace({
        widget: new EnvironmentBlockWidget(zone.name, zone.source),
        block: true,
      });
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    } else {
      if (revealed) continue;
      const replace = Decoration.replace({});
      deco.push(replace.range(zone.from, zone.to));
      atomics.push(replace.range(zone.from, zone.to));
    }
  }

  return {
    deco: Decoration.set(deco, true),
    atomics: RangeSet.of(atomics, true),
  };
};

/** Whether the preamble banner is collapsed (default) or expanded. */
export const preambleCollapsedField = StateField.define<boolean>({
  create: () => true,
  update: (value, tr) => {
    for (const effect of tr.effects) {
      if (effect.is(setPreambleCollapsed)) return effect.value;
    }
    return value;
  },
});

type BlocksValue = Materialized & { zones: BlockZone[]; key: string };

const buildBlocksValue = (state: EditorState): BlocksValue => {
  const zones = computeBlockZones(state);
  const collapsed = state.field(preambleCollapsedField);
  return {
    zones,
    key: revealKey(state, zones),
    ...materializeBlockZones(state, zones, collapsed),
  };
};

export const atomicBlocksField = StateField.define<BlocksValue>({
  create: buildBlocksValue,
  update: (value, tr) => {
    const treeChanged = syntaxTree(tr.state) !== syntaxTree(tr.startState);
    const collapseToggled = tr.effects.some((e) => e.is(setPreambleCollapsed));
    // The field instance survives compartment reconfigures (module-level
    // singleton), so an options change arrives as a new facet value only.
    const configChanged =
      tr.state.facet(visualConfigFacet) !==
      tr.startState.facet(visualConfigFacet);
    if (treeChanged || collapseToggled || configChanged) {
      return buildBlocksValue(tr.state);
    }

    if (tr.docChanged) {
      // The parse hasn't advanced yet (it will arrive as its own transaction):
      // keep the old zones, mapped through the edit, so positions stay valid.
      const zones: BlockZone[] = [];
      for (const zone of value.zones) {
        const from = tr.changes.mapPos(zone.from, 1);
        const to = tr.changes.mapPos(zone.to, -1);
        if (from < to) zones.push({ ...zone, from, to });
      }
      const collapsed = tr.state.field(preambleCollapsedField);
      return {
        zones,
        key: revealKey(tr.state, zones),
        ...materializeBlockZones(tr.state, zones, collapsed),
      };
    }

    if (tr.selection) {
      // Cursor-only movement: re-materialize only when the set of revealed
      // zones actually changed (cheap array scan, no tree walk).
      const key = revealKey(tr.state, value.zones);
      if (key === value.key) return value;
      const collapsed = tr.state.field(preambleCollapsedField);
      return {
        zones: value.zones,
        key,
        ...materializeBlockZones(tr.state, value.zones, collapsed),
      };
    }

    return value;
  },
  provide: (field) => [
    EditorView.decorations.from(field, (value) => value.deco),
    EditorView.atomicRanges.of((view) => view.state.field(field).atomics),
  ],
});

/**
 * Template-managed blocks are immutable in visual mode. A user can still
 * intentionally alter/remove the underlying `\input` after switching to Code.
 */
export const protectEmbeddedInputs = EditorState.changeFilter.of((tr) => {
  if (!tr.docChanged) return true;
  if (tr.annotation(externalDocumentSync)) return true;
  const zones = tr.startState
    .field(atomicBlocksField, false)
    ?.zones.filter((zone) => zone.kind === "embeddedInput");
  if (!zones?.length) return true;

  let blocked = false;
  tr.changes.iterChangedRanges((from, to) => {
    if (blocked) return;
    blocked = zones.some((zone) => {
      if (from === to) {
        // Typing exactly beside the command would turn a full-line input into
        // ordinary inline source and make its atomic protection disappear.
        return from >= zone.from && from <= zone.to;
      }
      const protectedFrom = Math.max(0, zone.from - 1);
      const protectedTo = Math.min(tr.startState.doc.length, zone.to + 1);
      // Also protect the line breaks immediately around the command: deleting
      // either one would merge the input into neighbouring prose.
      return from < protectedTo && to > protectedFrom;
    });
  });
  return !blocked;
});

/** Current block zones (empty when the visual mode is off). */
export const blockZones = (state: EditorState): BlockZone[] =>
  state.field(atomicBlocksField, false)?.zones ?? [];
