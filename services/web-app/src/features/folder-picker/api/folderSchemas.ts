import { z } from "zod";

export const BrowseEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
  is_dir: z.boolean(),
  is_hidden: z.boolean(),
});

export const BrowseResponseSchema = z.object({
  path: z.string(),
  parent: z.string().nullable(),
  // Корень смонтированной папки пользователя: выше него подниматься некуда,
  // а сам каталог уже пригоден для выбора.
  is_root: z.boolean().optional().default(false),
  entries: z.array(BrowseEntrySchema),
});

export const InspectedProjectSchema = z.object({
  id: z.string(),
  name: z.string(),
  pack_id: z.string(),
  template_id: z.string(),
  version: z.string(),
  engine: z.string(),
});

export const InspectResponseSchema = z.object({
  path: z.string(),
  exists: z.boolean(),
  is_dir: z.boolean(),
  has_project: z.boolean(),
  project: InspectedProjectSchema.nullable(),
});

export type BrowseEntry = z.infer<typeof BrowseEntrySchema>;
export type BrowseResponse = z.infer<typeof BrowseResponseSchema>;
export type InspectedProject = z.infer<typeof InspectedProjectSchema>;
export type InspectResponse = z.infer<typeof InspectResponseSchema>;
