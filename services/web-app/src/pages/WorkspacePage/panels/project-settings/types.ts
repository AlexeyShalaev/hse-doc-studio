import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";

export type Project = z.infer<typeof ProjectResponseSchema>;

export type PersonRole = "university" | "company";

// The response schema types `title`/`degree` as `string | null | undefined`,
// while the editors work with plain strings — hence the narrow local shape and
// the casts kept at the call boundary in ProjectSettingsView.
export type Person = {
  name: string;
  role: PersonRole;
  title?: string;
  degree?: string;
};

// Derive from the project schema so the optional `group` matches exactly under
// exactOptionalPropertyTypes (a hand-written `group?: string` rejects undefined).
export type AuthorEntry = NonNullable<Project["authors"]>[number];
