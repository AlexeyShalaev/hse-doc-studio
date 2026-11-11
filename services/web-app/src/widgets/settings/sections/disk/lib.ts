// Labels of the «Диск» categories in the settings dictionary. Order and
// colours live in @entities/docker-system (shared with «Диск раннера»).
const CATEGORY_LABEL_KEYS: Record<string, string> = {
  compile: "disk.categoryCompile",
  languagetool: "disk.categoryLanguagetool",
  office: "disk.categoryOffice",
  ai: "disk.categoryAi",
  app: "disk.categoryApp",
  cache: "disk.categoryCache",
  runtime: "disk.categoryRuntime",
  dangling: "disk.categoryDangling",
};

export const categoryLabelKey = (category: string): string =>
  CATEGORY_LABEL_KEYS[category] ?? "disk.categoryOtherShort";
