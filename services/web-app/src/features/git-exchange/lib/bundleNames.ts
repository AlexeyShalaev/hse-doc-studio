// Имена переносных файлов: обычный .bundle и зашифрованный .hseenc.

export const BUNDLE_ACCEPT = ".bundle,.hseenc";

export const isBundleName = (name: string): boolean => {
  const lower = name.toLowerCase();
  return lower.endsWith(".bundle") || lower.endsWith(".hseenc");
};

export const isEncryptedBundleName = (name: string): boolean =>
  name.toLowerCase().endsWith(".hseenc");
