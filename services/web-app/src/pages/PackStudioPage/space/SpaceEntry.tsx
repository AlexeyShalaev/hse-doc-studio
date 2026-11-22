import { Navigate, useLocation } from "react-router";
import {
  legacyToSpace,
  spacePath,
  usePackGit,
  type PackTree,
  type PackWorkspace,
} from "@entities/pack-studio";
import {
  NoPlace,
  readPlace,
  readSituation,
  resolveEntryPlace,
  writeInputs,
} from "@features/pack-space";
import { Spinner } from "@shared/ui";
import { WithSpaceData } from "./WithSpaceData";

/**
 * Куда открыть вход: последнее место, иначе версия с моими изменениями, иначе по умолчанию.
 * Ждёт список изменений (git), чтобы не пропустить свою работу; ошибка git входу не мешает.
 */
const EntryRedirect = ({
  workspace,
  tree,
}: {
  workspace: PackWorkspace;
  tree: PackTree;
}) => {
  const { pathname, search } = useLocation();
  const git = usePackGit(workspace.id, workspace.kind === "git");
  if (git.isPending && workspace.kind === "git") {
    return (
      <div className="ps-page flex justify-center" data-testid="space-loading">
        <Spinner size="lg" />
      </div>
    );
  }
  const legacy = legacyToSpace(workspace.id, pathname, search);
  const place = resolveEntryPlace(tree, {
    ref: legacy?.ref,
    template: legacy?.template,
    tab: legacy?.tab,
    last: readPlace(workspace.id),
    changed: git.data?.changed.map((file) => file.path),
  });
  if (!place) return <NoPlace workspace={workspace} tree={tree} />;
  const params = new URLSearchParams(legacy?.search ?? "");
  // Условия из памяти возвращаются, только если в адресе своих нет.
  if (
    Object.keys(place.inputs).length > 0 &&
    Object.keys(readSituation(params.toString()).inputs).length === 0
  ) {
    writeInputs(params, place.inputs);
  }
  return (
    <Navigate
      replace
      to={spacePath(workspace.id, place.ref, place.tab, params.toString())}
    />
  );
};

/**
 * Вход без версии: корень пространства и все старые адреса (`result`, `?file=`, `?view=files`,
 * `?newVersion=`). Решает, куда открыть, и переходит заменой записи истории: «назад» не
 * возвращает на перенаправление.
 */
export const SpaceEntry = () => (
  <WithSpaceData>
    {({ workspace, tree }) => (
      <EntryRedirect workspace={workspace} tree={tree} />
    )}
  </WithSpaceData>
);
