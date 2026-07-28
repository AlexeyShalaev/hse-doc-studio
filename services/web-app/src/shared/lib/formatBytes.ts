// GB/MB formatter for Docker image/disk sizes. GiB-based (1024^n) to match
// what `docker` itself reports in its human-readable size strings.
export const formatBytes = (bytes: number): string => {
  if (bytes <= 0) return "—";
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = bytes / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
};
