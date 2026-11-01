import { z } from "zod";

// Контракт PDF, выгруженных локальной Студией на сервер (docs/design/local-sync.md, раздел 2).
export const ProjectArtifactSchema = z.strictObject({
  id: z.string(),
  kind: z.literal("pdf"),
  doc_id: z.string(),
  file_name: z.string(),
  size: z.number(),
  sha256: z.string(),
  pages: z.number().nullable(),
  source_commit: z.string().nullable(),
  built_at: z.string().nullable(),
  uploaded_at: z.string(),
  uploaded_by_name: z.string().nullable(),
  client_name: z.string().nullable(),
  // Относительный адрес файла: открывается теми же правами, что и проект.
  file_url: z.string(),
});

export const ProjectArtifactListSchema = z.strictObject({
  items: z.array(ProjectArtifactSchema),
  max_pdf_bytes: z.number(),
  keep_per_document: z.number(),
});

// Ответ приёма файла (`PUT /git/-/projects/{id}/documents/{doc}/pdf`): локальная Студия читает его своим клиентом.
export const PdfUploadResultSchema = z.strictObject({
  artifact: ProjectArtifactSchema,
  // false: такой же файл уже был последним, новая запись не создана.
  created: z.boolean(),
});

export type ProjectArtifact = z.infer<typeof ProjectArtifactSchema>;
export type ProjectArtifactList = z.infer<typeof ProjectArtifactListSchema>;
