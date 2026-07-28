import { useEffect, useRef, useState } from "react";
import { useDebouncedCallback } from "use-debounce";
import type { z } from "zod";
import {
  type ProjectResponseSchema,
  useUpdateProject,
} from "@entities/project";
import type { UpdateProjectRequest } from "@shared/api/types";

type Project = z.infer<typeof ProjectResponseSchema>;
type UpdateProjectMutate = ReturnType<typeof useUpdateProject>["mutate"];
type MutateOptions = Parameters<UpdateProjectMutate>[1];

// The settings page inputs are driven entirely by the server project, so the
// old "save on every onChange" wrote project.json (and refreshed caches) once
// per keystroke — typing a name lagged badly. We keep unsaved edits in a local
// overlay so inputs stay instant, and only write to the backend once the user
// pauses typing. Deliberate clicks (toggles, add/remove, NDA) save right away.
//
// The overlay is reset by remounting (the panel is keyed on project.id), so the
// hook itself never has to reconcile against a different project.
const AUTOSAVE_DELAY_MS = 800;

export type UseProjectAutosave = {
  // The server project with the user's not-yet-flushed edits applied on top.
  effective: Project;
  // Accumulate an edit and schedule a debounced save (for typed-in fields).
  patch: (data: UpdateProjectRequest) => void;
  // Save immediately, merging any pending edits. Forwards mutate options so the
  // caller can chain follow-ups (e.g. instantiate NDA files after meta.nda).
  saveNow: (data: UpdateProjectRequest, options?: MutateOptions) => void;
  // Persist any pending edits right now (e.g. before a folder move).
  flush: () => void;
};

export const useProjectAutosave = (project: Project): UseProjectAutosave => {
  const { mutate: updateProject } = useUpdateProject();

  // Unsaved edits overlaid on the server project. Mirrored into a ref so the
  // debounced flush + saveNow read the latest value without stale closures.
  const [pending, setPending] = useState<UpdateProjectRequest>({});
  const pendingRef = useRef<UpdateProjectRequest>({});

  const send = (data: UpdateProjectRequest, options?: MutateOptions): void => {
    if (Object.keys(data).length === 0) return;
    updateProject({ id: project.id, data }, options);
  };

  const debouncedSave = useDebouncedCallback(() => {
    send(pendingRef.current);
  }, AUTOSAVE_DELAY_MS);

  const patch = (data: UpdateProjectRequest): void => {
    const next = { ...pendingRef.current, ...data };
    pendingRef.current = next;
    setPending(next);
    debouncedSave();
  };

  const saveNow = (
    data: UpdateProjectRequest,
    options?: MutateOptions,
  ): void => {
    debouncedSave.cancel();
    const next = { ...pendingRef.current, ...data };
    pendingRef.current = next;
    setPending(next);
    send(next, options);
  };

  const flush = (): void => {
    debouncedSave.cancel();
    send(pendingRef.current);
  };

  // Flush a pending autosave on unmount (navigating away, closing the panel) so
  // edits made within the debounce window aren't silently dropped.
  useEffect(
    () => () => {
      debouncedSave.flush();
    },
    [debouncedSave],
  );

  // The overlay only ever carries the fields this panel edits, so the merged
  // object is a valid Project at runtime; the cast just sidesteps the request
  // DTO's wider optionals (e.g. checks_override) that never appear in `pending`.
  const effective = { ...project, ...pending } as Project;
  return { effective, patch, saveNow, flush };
};
