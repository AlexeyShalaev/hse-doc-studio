import { z } from "zod";

export const SignModeSchema = z.enum([
  "image",
  "image_crypto",
  "crypto_invisible",
  "detached",
]);

export const SlotInfoSchema = z.object({
  png_path: z.string().nullable(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
  signing_identity_id: z.string().uuid().nullable().optional().default(null),
  sign_mode: SignModeSchema.optional().default("image"),
  sign_reason: z.string().optional().default(""),
});

export const PlacementSchema = z.object({
  enabled: z.boolean(),
  page: z.number(),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
  sign_date: z.string().nullable().optional().default(null),
});

// Контрольная точка, требующая подпись этого слота на конкретном документе.
export const SignatureProfileRefSchema = z.object({
  id: z.string(),
  name: z.record(z.string(), z.string()),
});

// Effective slot set computed by the backend for the CURRENT project. In team
// mode per-author slots are multiplied ("author--ivanov", label already carries
// the name) and applies_to/required_by reference document INSTANCE ids. When
// non-empty, the signatures UI must use these instead of the catalog slot defs
// (whose applies_to are pack definition ids and won't match instances).
export const RuntimeSignatureSlotSchema = z.object({
  id: z.string(),
  label: z.record(z.string(), z.string()),
  applies_to: z.array(z.string()),
  // Где подпись ОБЯЗАТЕЛЬНА и на какой точке: id документа → контрольные точки.
  // Пришло на смену `required_for: string[]`: обязательность зависит от точки
  // (ТЗ на КТ2 идёт без подписи научрука, на ГИА — обязательно с ней), и
  // отдельное поле у слота выразить это не могло.
  required_by: z
    .record(z.string(), z.array(SignatureProfileRefSchema))
    .default({}),
  default_placement: z.object({
    page: z.number(),
    x_mm: z.number(),
    y_mm: z.number(),
    width_mm: z.number(),
  }),
  owner: z.string().nullish().default(null),
});

export const SignaturesStateSchema = z.object({
  slots: z.record(z.string(), SlotInfoSchema),
  placements: z.record(z.string(), z.record(z.string(), PlacementSchema)),
  runtime_slots: z.array(RuntimeSignatureSlotSchema).default([]),
});

export const UploadSignatureResponseSchema = z.object({
  png_path: z.string(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
});

export const UpdatePlacementRequestSchema = z.object({
  enabled: z.boolean().optional(),
  page: z.number().optional(),
  x_mm: z.number().optional(),
  y_mm: z.number().optional(),
  width_mm: z.number().optional(),
  sign_date: z.string().optional(),
});
