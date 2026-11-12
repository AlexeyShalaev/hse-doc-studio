import { z } from "zod";

// Ревью-комментарии к тексту файлов (этап 5). Зеркало api/schemas/review.py;
// strictObject повторяет extra=forbid бэкенда.

const iso = z.string().min(1);

export const ThreadStatusSchema = z.enum(["open", "resolved"]);
export type ThreadStatus = z.infer<typeof ThreadStatusSchema>;

/** Цитата из исходника с контекстом (привязка по тексту файла). */
export const AnchorSchema = z.strictObject({
  kind: z.literal("text"),
  quote: z.string(),
  prefix: z.string(),
  suffix: z.string(),
  start: z.number().int(),
  end: z.number().int(),
});
export type Anchor = z.infer<typeof AnchorSchema>;

/** Прямоугольник на странице PDF в пунктах от левого верхнего угла. */
export const PdfRectSchema = z.strictObject({
  x: z.number(),
  y: z.number(),
  width: z.number().nonnegative(),
  height: z.number().nonnegative(),
});
export type PdfRect = z.infer<typeof PdfRectSchema>;

/** Место в PDF документа: комментарий из превью, текст которого не нашёлся в исходнике. */
export const PdfAnchorSchema = z.strictObject({
  kind: z.literal("pdf"),
  doc_id: z.string(),
  page: z.number().int().positive(),
  rects: z.array(PdfRectSchema),
  text: z.string(),
  build_sha: z.string(),
});
export type PdfAnchor = z.infer<typeof PdfAnchorSchema>;

export const ThreadAnchorSchema = z.discriminatedUnion("kind", [
  AnchorSchema,
  PdfAnchorSchema,
]);
export type ThreadAnchor = z.infer<typeof ThreadAnchorSchema>;

export const ReviewCommentSchema = z.strictObject({
  id: z.string(),
  author_id: z.string().nullable(),
  author_name: z.string(),
  body: z.string(),
  mentions: z.array(z.string()),
  created_at: iso,
  edited_at: iso.nullable(),
});
export type ReviewComment = z.infer<typeof ReviewCommentSchema>;

export const ReviewThreadSchema = z.strictObject({
  id: z.string(),
  path: z.string(),
  anchor: ThreadAnchorSchema,
  status: ThreadStatusSchema,
  created_by: z.string().nullable(),
  created_by_name: z.string(),
  created_at: iso,
  updated_at: iso,
  resolved_by_name: z.string().nullable(),
  resolved_at: iso.nullable(),
  comments: z.array(ReviewCommentSchema),
});
export type ReviewThread = z.infer<typeof ReviewThreadSchema>;

export const ReviewThreadListSchema = z.strictObject({
  items: z.array(ReviewThreadSchema),
});

/** Тред с цитатой из исходника (не PDF-якорь): такие показывает редактор. */
export type TextReviewThread = ReviewThread & { anchor: Anchor };

export const isTextThread = (
  thread: ReviewThread,
): thread is TextReviewThread => thread.anchor.kind === "text";

/**
 * Где тред на текущем PDF документа. `exact`: прямоугольники точные; иначе это
 * строка SyncTeX или прежнее место, и превью уточняет его поиском `text`.
 */
export const PdfPlaceSchema = z.strictObject({
  page: z.number().int().positive(),
  rects: z.array(PdfRectSchema),
  text: z.string(),
  exact: z.boolean(),
});
export type PdfPlace = z.infer<typeof PdfPlaceSchema>;

export const PlacedThreadSchema = z.strictObject({
  thread: ReviewThreadSchema,
  place: PdfPlaceSchema.nullable(),
});
export type PlacedThread = z.infer<typeof PlacedThreadSchema>;

export const DocumentReviewSchema = z.strictObject({
  build_sha: z.string().nullable(),
  items: z.array(PlacedThreadSchema),
});
export type DocumentReview = z.infer<typeof DocumentReviewSchema>;

export const CreatePdfThreadRequestSchema = z.strictObject({
  doc_id: z.string().min(1),
  page: z.number().int().positive(),
  rects: z.array(PdfRectSchema),
  text: z.string(),
  body: z.string(),
  mentions: z.array(z.string()),
});
export type NewPdfThread = z.infer<typeof CreatePdfThreadRequestSchema>;

export const MentionCandidateSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
});
export type MentionCandidate = z.infer<typeof MentionCandidateSchema>;

export const MentionCandidateListSchema = z.strictObject({
  items: z.array(MentionCandidateSchema),
});

export type NewThread = {
  path: string;
  anchor: Anchor;
  body: string;
  mentions: string[];
};
