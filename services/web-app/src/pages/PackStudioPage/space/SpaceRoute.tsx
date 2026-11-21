import { Navigate, useLocation, useParams } from "react-router";
import { PACK_STUDIO_PATH, isSpaceTab, spacePath } from "@entities/pack-studio";
import { SpaceProvider, SpaceScreen, hasVersion } from "@features/pack-space";
import { WithSpaceData } from "./WithSpaceData";

/**
 * Вкладка версии: `/w/:ws/t/:pack/:template/:version/:tab`. Нет такой версии в дереве (старая
 * ссылка, версию удалили): вход подберёт место сам. Неизвестная вкладка: «Результат».
 */
export const SpaceRoute = () => {
  const {
    workspaceId = "",
    pack = "",
    template = "",
    version = "",
    tab,
  } = useParams<{
    workspaceId: string;
    pack: string;
    template: string;
    version: string;
    tab: string;
  }>();
  const { search } = useLocation();
  const ref = { pack, template, version };
  if (!isSpaceTab(tab)) {
    return (
      <Navigate replace to={spacePath(workspaceId, ref, "result", search)} />
    );
  }
  return (
    <WithSpaceData>
      {({ workspace, tree }) =>
        hasVersion(tree, ref) ? (
          <SpaceProvider
            workspace={workspace}
            tree={tree}
            versionRef={ref}
            tab={tab}
          >
            <SpaceScreen />
          </SpaceProvider>
        ) : (
          <Navigate
            replace
            to={`${PACK_STUDIO_PATH}/w/${encodeURIComponent(workspaceId)}${search}`}
          />
        )
      }
    </WithSpaceData>
  );
};
