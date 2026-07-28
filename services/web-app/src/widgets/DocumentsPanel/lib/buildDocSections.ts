import type { z } from "zod";
import type { DocumentResponseSchema } from "@entities/document";

export type DocumentItem = z.infer<typeof DocumentResponseSchema>;

// Minimal structural slice of a project author (accepts the zod-parsed
// AuthorDto, whose optional fields carry `| undefined`).
export type AuthorLike = {
  name: string;
  slug?: string | null | undefined;
};

export type DocNavSection = {
  key: string;
  // null → flat solo view; the generic «Документы» header is used instead.
  title: string | null;
  // Author sections already name the owner in the header, so document rows
  // drop the " — owner" suffix from the type name.
  hideOwnerSuffix: boolean;
  docs: DocumentItem[];
};

// Team projects (any doc with an owner) group the nav: shared docs first,
// then one section per author in project.authors order. Solo projects (no
// owned docs) keep the flat single-section view untouched.
export const buildDocSections = (
  docs: DocumentItem[],
  authors: AuthorLike[],
  sharedTitle: string,
): DocNavSection[] => {
  const owned = docs.filter((doc) => doc.owner != null);
  if (owned.length === 0) {
    return [{ key: "all", title: null, hideOwnerSuffix: false, docs }];
  }
  const sections: DocNavSection[] = [];
  const shared = docs.filter((doc) => doc.owner == null);
  if (shared.length > 0) {
    sections.push({
      key: "shared",
      title: sharedTitle,
      hideOwnerSuffix: false,
      docs: shared,
    });
  }
  const claimed = new Set<string>();
  for (const author of authors) {
    if (author.slug == null) continue;
    const own = owned.filter((doc) => doc.owner === author.slug);
    if (own.length === 0) continue;
    claimed.add(author.slug);
    sections.push({
      key: `author:${author.slug}`,
      // The section header is the owner's ФИО; author.name covers docs the
      // backend sent without owner_name.
      title: own[0]?.owner_name ?? author.name,
      hideOwnerSuffix: true,
      docs: own,
    });
  }
  // Defensive: owners missing from project.authors still get a section,
  // appended after the known authors in document order.
  for (const doc of owned) {
    const owner = doc.owner ?? "";
    if (claimed.has(owner)) continue;
    claimed.add(owner);
    sections.push({
      key: `author:${owner}`,
      title: doc.owner_name ?? owner,
      hideOwnerSuffix: true,
      docs: owned.filter((d) => d.owner === owner),
    });
  }
  return sections;
};
