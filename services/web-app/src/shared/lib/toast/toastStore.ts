import { create } from "zustand";

export type ToastKind = "info" | "success" | "warning" | "error";

export type ToastAction = {
  label: string;
  onClick: () => void;
};

export type Toast = {
  id: string;
  kind: ToastKind;
  title?: string;
  message: string;
  duration?: number;
  action?: ToastAction;
};

type Store = {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
  clear: () => void;
};

export const useToastStore = create<Store>((set, get) => ({
  toasts: [],
  push: (t) => {
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    const ms = t.duration ?? 5000;
    if (ms > 0) {
      setTimeout(() => {
        get().dismiss(id);
      }, ms);
    }
    return id;
  },
  dismiss: (id) => {
    set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
  },
  clear: () => {
    set({ toasts: [] });
  },
}));

const push = (t: Omit<Toast, "id">) => useToastStore.getState().push(t);

export type ToastOptions = {
  title?: string;
  action?: ToastAction;
  duration?: number;
};

const mk = (
  kind: ToastKind,
  message: string,
  titleOrOpts?: string | ToastOptions,
) => {
  if (typeof titleOrOpts === "string" || titleOrOpts === undefined) {
    return push({
      kind,
      message,
      ...(titleOrOpts ? { title: titleOrOpts } : {}),
    });
  }
  return push({ kind, message, ...titleOrOpts });
};

export const toast = {
  info: (message: string, titleOrOpts?: string | ToastOptions) =>
    mk("info", message, titleOrOpts),
  success: (message: string, titleOrOpts?: string | ToastOptions) =>
    mk("success", message, titleOrOpts),
  warning: (message: string, titleOrOpts?: string | ToastOptions) =>
    mk("warning", message, titleOrOpts),
  error: (message: string, titleOrOpts?: string | ToastOptions) =>
    mk("error", message, titleOrOpts),
};
