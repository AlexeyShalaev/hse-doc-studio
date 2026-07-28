import { Annotation, StateEffect } from "@codemirror/state";

/** Collapse/expand the preamble banner (dispatched by its widgets). */
export const setPreambleCollapsed = StateEffect.define<boolean>();

/**
 * Marks a controlled-value replacement coming from the React host (revert,
 * quick fix, file refresh). User edits never carry this annotation, so visual
 * input references stay protected without blocking legitimate external sync.
 */
export const externalDocumentSync = Annotation.define<boolean>();
