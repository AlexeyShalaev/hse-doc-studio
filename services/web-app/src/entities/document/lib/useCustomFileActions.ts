import {
  useUploadCustomFile,
  useRemoveCustomFile,
} from "../api/documentQueries";

export type CustomFileActions = {
  upload: (file: File) => Promise<void>;
  remove: (deleteFile?: boolean) => Promise<void>;
  isUploading: boolean;
  isRemoving: boolean;
};

/**
 * Thin wrapper around the upload/remove custom-file mutations, parameterized
 * by project/doc so both entry points (DocumentNav row menu, DocumentTabs
 * header) share one hook instead of duplicating mutate() call sites.
 */
export const useCustomFileActions = (
  projectId: string,
  docId: string,
): CustomFileActions => {
  const upload = useUploadCustomFile();
  const remove = useRemoveCustomFile();

  return {
    upload: async (file: File) => {
      await upload.mutateAsync({ projectId, docId, file });
    },
    remove: async (deleteFile = false) => {
      await remove.mutateAsync({ projectId, docId, deleteFile });
    },
    isUploading: upload.isPending,
    isRemoving: remove.isPending,
  };
};
