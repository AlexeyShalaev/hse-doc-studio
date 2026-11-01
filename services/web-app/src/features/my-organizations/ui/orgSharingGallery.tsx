import type { OrgSharingPolicy } from "@entities/share-link";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { OrgSharingPolicyView } from "./OrgSharingPolicySection";

const noop = () => undefined;
const DEFAULT: OrgSharingPolicy = {
  links: "any",
  max_link_role: "editor",
  nda_public_links: false,
  external_invites: true,
  editable: true,
};

/** «Общий доступ» организации (10.5). */
export const getOrgSharingGallery = (): GalleryGroup[] => [
  {
    id: "org-sharing",
    title: "Организация: общий доступ",
    entries: [
      {
        id: "org_sharing_admin",
        title: "Админ организации: правит",
        frame: "window",
        width: 620,
        render: () => (
          <OrgSharingPolicyView
            orgName="МСПИН 2025"
            status="ready"
            policy={DEFAULT}
            onSave={noop}
          />
        ),
      },
      {
        id: "org_sharing_strict",
        title: "Строгая политика",
        frame: "window",
        width: 620,
        render: () => (
          <OrgSharingPolicyView
            orgName="МСПИН 2025"
            status="ready"
            policy={{
              ...DEFAULT,
              links: "org_only",
              max_link_role: "reviewer",
              external_invites: false,
            }}
            onSave={noop}
          />
        ),
      },
      {
        id: "org_sharing_member",
        title: "Участник: только просмотр",
        frame: "window",
        width: 620,
        render: () => (
          <OrgSharingPolicyView
            orgName="МСПИН 2025"
            status="ready"
            policy={{ ...DEFAULT, editable: false }}
            onSave={noop}
          />
        ),
      },
    ],
  },
];
