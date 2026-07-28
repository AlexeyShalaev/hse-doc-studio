import { z } from "zod";

const LocalizedStringSchema = z.record(z.string(), z.string());

export const SubmissionProfileSchema = z.object({
  id: z.string(),
  name: LocalizedStringSchema,
  description: LocalizedStringSchema,
  // Backend may omit these or return them empty depending on the endpoint;
  // .nullish() tolerates both null and undefined.
  items: z
    .array(
      z.object({
        doc_id: z.string(),
        signatures: z.array(z.string()),
        // Гейты состава, которые применяет бэкенд в build_item_list. Сам
        // ДОКУМЕНТ может быть в проекте, а в комплект точки не входить: thesis
        // на КТ2 ВКР — только проектный формат, Текст программы не сдаётся под
        // NDA. Без них клиент показал бы блокер, которого при сборке не будет.
        skip_if_nda: z.boolean().default(false),
        supported_kinds: z.array(z.string()).default(["research", "project"]),
      }),
    )
    .nullish(),
  extra_items: z
    .array(
      z.object({
        source: z.string(),
        output_name: z.string(),
        format: z.string().nullish(),
        // Тот же гейт, что у пунктов-документов: «Ссылка на код.txt» на КТ2
        // входит в пакет только у исследовательского формата.
        supported_kinds: z.array(z.string()).default(["research", "project"]),
      }),
    )
    .nullish(),
});

export const SubmissionRecordSchema = z.object({
  id: z.string(),
  profile_id: z.string().nullish(),
  profile_name: z.record(z.string(), z.string()).nullish(),
  created_at: z.string(),
  output_path: z.string().nullable().optional(),
  output_dir: z.string().nullable().optional(),
  size_bytes: z.number().nullable().optional(),
  archive_format: z.string().nullish(),
  doc_count: z.number().nullish(),
});

export const CreateSubmissionRequestSchema = z.object({
  profile_id: z.string(),
  items: z.array(
    z.object({
      doc_id: z.string(),
      signatures: z.array(z.string()),
    }),
  ),
  extra_items: z
    .array(
      z.object({
        source: z.string(),
        output_name: z.string(),
        format: z.string().nullish(),
        // Тот же гейт, что у пунктов-документов: «Ссылка на код.txt» на КТ2
        // входит в пакет только у исследовательского формата.
        supported_kinds: z.array(z.string()).default(["research", "project"]),
      }),
    )
    .optional(),
  archive_format: z.enum(["zip", "targz", "7z", "rar"]).optional(),
  // REQUIRED for team projects: whose submission package is being built (their
  // personal docs + shared docs + their declaration).
  author_slug: z.string().optional(),
  // doc_id -> convert-to-pdf yes/no, for custom (non-template) documents in
  // this package. Empty/omitted when the package has no custom docs, or the
  // user didn't need to be asked (all custom docs already PDF).
  custom_doc_decisions: z.record(z.string(), z.boolean()).optional(),
});

export const CustomFilePreflightItemSchema = z.object({
  doc_id: z.string(),
  doc_name: z.record(z.string(), z.string()),
  original_filename: z.string(),
  ext: z.string(),
  convertible: z.boolean(),
  default_decision: z.boolean().nullable().optional(),
});

// Backend returns a plain JSON array (response_model=list[...]), not a
// wrapped `{items: [...]}` envelope.
export const CustomFilePreflightResponseSchema = z.array(
  CustomFilePreflightItemSchema,
);
