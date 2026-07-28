import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";

// Managed office Docker services (mirrors the LanguageTool images API):
//   convert — Gotenberg, converts .pptx → PDF on build for the inline preview;
//   editor  — ONLYOFFICE Document Server, the embedded slides editor.
export const OFFICE_SERVICES = ["convert", "editor"] as const;
export type OfficeServiceId = (typeof OFFICE_SERVICES)[number];

export const OfficeServiceContainerSchema = z.object({
  present: z.boolean(),
  running: z.boolean(),
  status_text: z.string().nullable().default(null),
});

export type OfficeServiceContainer = z.infer<
  typeof OfficeServiceContainerSchema
>;

export const OfficeServiceStatusSchema = z.object({
  // Kept as a plain string (not an enum) so an unknown service added on the
  // backend later doesn't break the whole status response.
  service: z.string(),
  label_hint: z.string().default(""),
  active_image: z.string(),
  image_installed: z.boolean(),
  container: OfficeServiceContainerSchema,
});

export type OfficeServiceStatus = z.infer<typeof OfficeServiceStatusSchema>;

export const OfficeServicesStatusSchema = z.object({
  services: z.array(OfficeServiceStatusSchema),
});

export type OfficeServicesStatus = z.infer<typeof OfficeServicesStatusSchema>;

export const OfficeServiceImageSchema = z.object({
  tag: z.string(),
  size: z.number().nonnegative().default(0),
  created: z.string().nullable().default(null),
  active: z.boolean().default(false),
  installed: z.boolean().default(true),
});

export type OfficeServiceImage = z.infer<typeof OfficeServiceImageSchema>;

export const OfficeServiceImagesSchema = z.object({
  images: z.array(OfficeServiceImageSchema),
});

export type OfficeServiceImages = z.infer<typeof OfficeServiceImagesSchema>;

// Remote tags mirror the LanguageTool /images/remote payload (objects with
// name/size/date); a bare string item is tolerated and normalized.
export const OfficeServiceRemoteTagSchema = z.union([
  z.object({
    name: z.string(),
    size_bytes: z.number().int().nonnegative().default(0),
    last_updated: z.string().nullable().default(null),
  }),
  z.string().transform((name) => ({
    name,
    size_bytes: 0,
    last_updated: null as string | null,
  })),
]);

export type OfficeServiceRemoteTag = z.output<
  typeof OfficeServiceRemoteTagSchema
>;

export const OfficeServiceRemoteTagsSchema = z.object({
  tags: z.array(OfficeServiceRemoteTagSchema),
});

export type OfficeServiceRemoteTags = z.output<
  typeof OfficeServiceRemoteTagsSchema
>;

export const SetActiveOfficeServiceImageSchema = z.object({
  image: z.string(),
});

export type SetActiveOfficeServiceImage = z.infer<
  typeof SetActiveOfficeServiceImageSchema
>;

// "repo/name:tag" → "repo/name" (the tag separator is a colon *after* the last
// slash; a colon before it would belong to a registry port).
export const officeImageRepo = (image: string): string => {
  const colon = image.lastIndexOf(":");
  const slash = image.lastIndexOf("/");
  return colon > slash ? image.slice(0, colon) : image;
};

// The images list carries bare tags; compose the full ref unless the entry
// already looks like one.
export const officeImageRef = (repo: string, tag: string): string =>
  tag.includes("/") || tag.includes(":") ? tag : `${repo}:${tag}`;

export const officeServicesApi = {
  status: () =>
    apiClient
      .get(`/office-services/status`)
      .then(parseResp(OfficeServicesStatusSchema)),

  images: (service: OfficeServiceId) =>
    apiClient
      .get(`/office-services/${service}/images`)
      .then(parseResp(OfficeServiceImagesSchema)),

  listRemoteTags: (service: OfficeServiceId) =>
    apiClient
      .get(`/office-services/${service}/images/remote`)
      .then(parseResp(OfficeServiceRemoteTagsSchema)),

  setActive: (service: OfficeServiceId, image: string) =>
    apiClient
      .post(`/office-services/${service}/images/active`, { image })
      .then(parseResp(SetActiveOfficeServiceImageSchema)),

  installStreamUrl: (service: OfficeServiceId, image: string) =>
    `${env.VITE_API_BASE_URL}/api/v1/office-services/${service}/images/install?image=${encodeURIComponent(image)}`,
};
