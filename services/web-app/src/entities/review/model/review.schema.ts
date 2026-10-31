import { z } from "zod";

// Ревью-комментарии к тексту файлов (этап 5). Зеркало api/schemas/review.py;
// strictObject повторяет extra=forbid бэкенда.

const iso = z.string().min(1);

export const ThreadStatusSchema = z.enum(["open", "resolved"]);
export type ThreadStatus = z.infer<typeof ThreadStatusSchema>;

export const AnchorSchema = z.strictObject({
  quote: z.string(),
  prefix: z.string(),
  suffix: z.string(),
  start: z.number().int(),
  end: z.number().int(),
});
export type Anchor = z.infer<typeof AnchorSchema>;

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
  anchor: AnchorSchema,
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
