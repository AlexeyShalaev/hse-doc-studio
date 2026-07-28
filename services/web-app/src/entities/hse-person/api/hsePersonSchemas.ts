import { z } from "zod";

export const HseFacetOptionSchema = z.object({
  value: z.string(),
  label: z.string(),
});

export type HseFacetOption = z.infer<typeof HseFacetOptionSchema>;

export const HsePersonSummarySchema = z.object({
  id: z.string(),
  full_name: z.string(),
  profile_url: z.string(),
  photo_url: z.string(),
  affiliation: z.string(),
});

export type HsePersonSummary = z.infer<typeof HsePersonSummarySchema>;

export const HsePersonDetailSchema = z.object({
  id: z.string(),
  full_name: z.string(),
  position: z.string(),
  department: z.string(),
  degree: z.string(),
  profile_url: z.string(),
  photo_url: z.string(),
});

export type HsePersonDetail = z.infer<typeof HsePersonDetailSchema>;

export const HseSearchResponseSchema = z.object({
  persons: z.array(HsePersonSummarySchema),
  interests: z.array(HseFacetOptionSchema),
});

export type HseSearchResponse = z.infer<typeof HseSearchResponseSchema>;

export const HseFacetsResponseSchema = z.object({
  campuses: z.array(HseFacetOptionSchema),
  departments: z.array(HseFacetOptionSchema),
  categories: z.array(HseFacetOptionSchema),
  sciranks: z.array(HseFacetOptionSchema),
  positions: z.array(HseFacetOptionSchema),
});

export type HseFacetsResponse = z.infer<typeof HseFacetsResponseSchema>;
