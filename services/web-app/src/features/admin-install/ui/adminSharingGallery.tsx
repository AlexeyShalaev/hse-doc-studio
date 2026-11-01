import type { AdminSharingSettings } from "@entities/share-link";
import type { GalleryGroup } from "@shared/lib/stateGallery";
import { AdminSharingSettingsView } from "./AdminSharingSettings";

const noop = () => undefined;
const DEFAULT: AdminSharingSettings = {
  links_enabled: true,
  max_link_role: "editor",
  project_invites_allow_signup: true,
  fields: {
    "sharing.links_enabled": { source: "default", locked: false },
    "sharing.max_link_role": { source: "default", locked: false },
    "registration.project_invites_allow_signup": {
      source: "default",
      locked: false,
    },
  },
};

/** Админка: «Общий доступ» (10.5). */
export const getAdminSharingGallery = (): GalleryGroup[] => [
  {
    id: "admin-sharing",
    title: "Админка: общий доступ",
    entries: [
      {
        id: "admin_sharing_default",
        title: "По умолчанию",
        frame: "window",
        width: 760,
        render: () => (
          <AdminSharingSettingsView settings={DEFAULT} onSave={noop} />
        ),
      },
      {
        id: "admin_sharing_env",
        title: "Ссылки заданы окружением",
        frame: "window",
        width: 760,
        render: () => (
          <AdminSharingSettingsView
            settings={{
              ...DEFAULT,
              links_enabled: false,
              fields: {
                ...DEFAULT.fields,
                "sharing.links_enabled": { source: "env", locked: true },
              },
            }}
            onSave={noop}
          />
        ),
      },
    ],
  },
];
