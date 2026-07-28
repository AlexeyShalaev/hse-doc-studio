export const compileApi = {
  streamUrl: (projectId: string, docId: string, compileId: string): string =>
    `/api/v1/projects/${projectId}/documents/${docId}/compiles/${compileId}/stream`,
};
