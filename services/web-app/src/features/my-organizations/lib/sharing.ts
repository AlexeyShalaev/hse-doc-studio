import type {
  LinkRole,
  OrgLinksMode,
  OrgSharingPolicy,
} from "@entities/share-link";

export const SHARING_ROLES: readonly LinkRole[] = [
  "reader",
  "reviewer",
  "editor",
];
export const SHARING_MODES: readonly OrgLinksMode[] = [
  "any",
  "org_only",
  "off",
];

/** Ужесточение: ссылки запрещаются или сужаются, предел роли падает, NDA-ссылки закрываются. */
export const tightens = (
  before: OrgSharingPolicy,
  after: OrgSharingPolicy,
): boolean =>
  SHARING_MODES.indexOf(after.links) > SHARING_MODES.indexOf(before.links) ||
  SHARING_ROLES.indexOf(after.max_link_role) <
    SHARING_ROLES.indexOf(before.max_link_role) ||
  (before.nda_public_links && !after.nda_public_links);
