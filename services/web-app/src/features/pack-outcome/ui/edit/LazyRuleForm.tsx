import { lazy } from "react";
import { loadPackFormsNamespace } from "@shared/lib/i18n/packFormsNamespace";

// Мини-форма записи манифеста: свой чанк и словарь форм, грузятся по первому «Править правило».
export const LazyRuleForm = lazy(() =>
  Promise.all([
    import("@features/pack-forms/rule"),
    loadPackFormsNamespace(),
  ]).then(([m]) => ({ default: m.RuleRecordForm })),
);
