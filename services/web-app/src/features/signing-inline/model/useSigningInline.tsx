import { useReducer, type ReactNode } from "react";
import { SignMethodCard } from "../ui/SignMethodCard";
import { SignPrimary } from "../ui/SignPrimary";
import {
  INITIAL_INLINE_UI,
  type InlineUi,
  type InlineUiState,
  type SigningInlineContext,
} from "./types";

/** Блоки подписи для точки расширения страницы подписанта (`SigningExtension`). */
export type SigningInlineExtension = {
  method: (ctx: SigningInlineContext) => ReactNode;
  primary: (ctx: SigningInlineContext) => ReactNode;
};

const merge = (
  state: InlineUiState,
  patch: Partial<InlineUiState>,
): InlineUiState => ({ ...state, ...patch });

/**
 * Подпись прямо на странице подписанта (срез W5, docs/design/signing-route.md, 3.2):
 * блок «Как подписать» и главная кнопка. Выбор человека (способ, ключ, файлы подписи)
 * живёт здесь, поэтому блок и кнопка, стоящие в разных местах страницы, видят одно и то же.
 * Согласующему без слотов блоки не нужны: обе функции возвращают null.
 */
export const useSigningInline = (
  initial: Partial<InlineUiState> = {},
): SigningInlineExtension => {
  const [state, patch] = useReducer(merge, {
    ...INITIAL_INLINE_UI,
    ...initial,
  });
  const ui: InlineUi = { state, patch };
  const hasSlots = (ctx: SigningInlineContext) =>
    ctx.task.me.method !== null || ctx.task.me.methods.length > 0;
  return {
    method: (ctx) =>
      hasSlots(ctx) ? <SignMethodCard ctx={ctx} ui={ui} /> : null,
    primary: (ctx) =>
      hasSlots(ctx) ? <SignPrimary ctx={ctx} ui={ui} /> : null,
  };
};
