import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PackStaleFileError,
  cacheModelResult,
  packStudioApi,
  packStudioKeys,
  type PackModelActionRequest,
  type PackVersionModel,
  type PackVersionRef,
  type PackYamlOp,
} from "@entities/pack-studio";

/** Манифест, который правит форма: от каталога версии. */
export type ModelFile = "version.yaml" | `files/${string}/doc.yaml`;

export const docManifest = (docId: string): ModelFile =>
  `files/${docId}/doc.yaml`;

type EditVars = { file: ModelFile; ops: PackYamlOp[] };

export type ModelEditor = {
  workspaceId: string;
  versionRef: PackVersionRef;
  model: PackVersionModel;
  readOnly: boolean;
  /** Правка ушла на сервер: пока идёт, поля не теряют фокус, но кнопки заняты. */
  busy: boolean;
  error: unknown;
  /** Файл поменяли мимо формы: модель перечитана, правку нужно повторить. */
  stale: boolean;
  clearError: () => void;
  /** Точечные правки одного манифеста; true, если записаны. */
  edit: (file: ModelFile, ops: PackYamlOp[]) => Promise<boolean>;
  /** Операция на несколько файлов (поле, документ, перевод); true, если сделана. */
  act: (body: PackModelActionRequest) => Promise<boolean>;
};

const EditorContext = createContext<ModelEditor | null>(null);

export const useModelEditor = (): ModelEditor => {
  const editor = useContext(EditorContext);
  if (editor === null) throw new Error("ModelEditor is missing");
  return editor;
};

const etagOf = (model: PackVersionModel | undefined, file: ModelFile) => {
  if (!model) return null;
  if (file === "version.yaml") return model.manifest.etag;
  const id = file.split("/")[1];
  return model.documents.find((d) => d.id === id)?.manifest?.etag ?? null;
};

export type ModelEditorProviderProps = {
  workspaceId: string;
  versionRef: PackVersionRef;
  model: PackVersionModel;
  /** Файлы на диске поменялись: проверки, класс версии, панель git. */
  onSaved: (changed: string[]) => void;
  children: ReactNode;
};

/**
 * Правки формы идут по одной (общая очередь мутаций), каждая с `If-Match` по
 * ETag из последнего ответа: следующая правка опирается на текст после
 * предыдущей. Ответ сервера (модель после правки) ложится в кэш запроса.
 */
export const ModelEditorProvider = ({
  workspaceId,
  versionRef,
  model,
  onSaved,
  children,
}: ModelEditorProviderProps) => {
  const client = useQueryClient();
  const { pack, template, version } = versionRef;
  const key = useMemo(
    () => packStudioKeys.model(workspaceId, { pack, template, version }),
    [workspaceId, pack, template, version],
  );
  const [stale, setStale] = useState(false);
  const scope = { id: `pack-model:${workspaceId}` };

  const apply = useCallback(
    (next: PackVersionModel) => {
      cacheModelResult(client, workspaceId, { pack, template, version }, next);
      setStale(false);
      onSaved(next.changed);
    },
    [client, workspaceId, pack, template, version, onSaved],
  );

  const onError = useCallback(
    (error: unknown) => {
      if (error instanceof PackStaleFileError) {
        setStale(true);
        void client.invalidateQueries({ queryKey: key });
      }
    },
    [client, key],
  );

  const patch = useMutation({
    scope,
    mutationFn: ({ file, ops }: EditVars) =>
      packStudioApi.patchVersionModel(
        workspaceId,
        versionRef,
        { file, ops },
        etagOf(client.getQueryData<PackVersionModel>(key), file),
      ),
    onSuccess: apply,
    onError,
  });

  const action = useMutation({
    scope,
    mutationFn: (body: PackModelActionRequest) =>
      packStudioApi.versionModelAction(
        workspaceId,
        versionRef,
        body,
        etagOf(client.getQueryData<PackVersionModel>(key), "version.yaml"),
      ),
    onSuccess: apply,
    onError,
  });

  const { mutateAsync: patchAsync, reset: resetPatch } = patch;
  const { mutateAsync: actAsync, reset: resetAction } = action;

  const edit = useCallback(
    async (file: ModelFile, ops: PackYamlOp[]) => {
      if (ops.length === 0) return true;
      resetAction();
      try {
        await patchAsync({ file, ops });
        return true;
      } catch {
        return false;
      }
    },
    [patchAsync, resetAction],
  );

  const act = useCallback(
    async (body: PackModelActionRequest) => {
      resetPatch();
      try {
        await actAsync(body);
        return true;
      } catch {
        return false;
      }
    },
    [actAsync, resetPatch],
  );

  const value = useMemo<ModelEditor>(
    () => ({
      workspaceId,
      versionRef,
      model,
      readOnly: model.read_only !== null,
      busy: patch.isPending || action.isPending,
      error: patch.error ?? action.error,
      stale,
      clearError: () => {
        resetPatch();
        resetAction();
        setStale(false);
      },
      edit,
      act,
    }),
    [
      workspaceId,
      versionRef,
      model,
      patch.isPending,
      action.isPending,
      patch.error,
      action.error,
      stale,
      edit,
      act,
      resetPatch,
      resetAction,
    ],
  );

  return (
    <EditorContext.Provider value={value}>{children}</EditorContext.Provider>
  );
};
