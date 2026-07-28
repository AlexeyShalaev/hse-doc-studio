import { useQuery } from "@tanstack/react-query";
import { folderApi } from "./folderApi";

export const folderKeys = {
  all: ["folder-picker"] as const,
  browse: (path: string | null) => [...folderKeys.all, "browse", path] as const,
  inspect: (path: string) => [...folderKeys.all, "inspect", path] as const,
};

export const useBrowseFolder = (path: string | null, enabled = true) =>
  useQuery({
    queryKey: folderKeys.browse(path),
    queryFn: () => folderApi.browse(path),
    enabled,
    retry: false,
  });

export const useInspectFolder = (path: string, enabled = true) =>
  useQuery({
    queryKey: folderKeys.inspect(path),
    queryFn: () => folderApi.inspect(path),
    enabled: enabled && path.trim().length > 0,
    retry: false,
  });
