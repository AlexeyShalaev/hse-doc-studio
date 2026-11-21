import { Link, Navigate, useLocation, useParams } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  legacyToSpace,
  spacePath,
} from "@entities/pack-studio";
import {
  readPlace,
  readSituation,
  resolveEntryPlace,
  writeInputs,
} from "@features/pack-space";
import { EmptyState } from "@shared/ui";
import { WithSpaceData } from "./WithSpaceData";

/**
 * Вход без версии: корень пространства и все старые адреса (`result`, `?file=`, `?view=files`,
 * `?newVersion=`). Решает, куда открыть, и переходит заменой записи истории: «назад» не
 * возвращает на перенаправление.
 */
export const SpaceEntry = () => {
  const { t } = useTranslation("packSpace");
  const { workspaceId = "" } = useParams<{ workspaceId: string }>();
  const { pathname, search } = useLocation();
  return (
    <WithSpaceData>
      {({ tree }) => {
        const legacy = legacyToSpace(workspaceId, pathname, search);
        const place = resolveEntryPlace(tree, {
          ref: legacy?.ref,
          template: legacy?.template,
          tab: legacy?.tab,
          last: readPlace(workspaceId),
        });
        if (!place) {
          return (
            <div className="ps-page">
              <EmptyState
                framed
                title={t("shell.entry.noVersionsTitle")}
                description={t("shell.entry.noVersionsLead")}
                action={
                  <Link className="btn sm" to={PACK_STUDIO_PATH}>
                    {t("shell.back")}
                  </Link>
                }
                testId="space-no-versions"
              />
            </div>
          );
        }
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
            to={spacePath(workspaceId, place.ref, place.tab, params.toString())}
          />
        );
      }}
    </WithSpaceData>
  );
};
