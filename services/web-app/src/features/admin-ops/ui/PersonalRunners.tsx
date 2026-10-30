import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { ConfirmByName } from "@shared/ui";
import type { AdminRunner } from "@entities/session";
import {
  usePersonalRunners,
  usePersonalRunnersEnabled,
  useRevokeRunner,
  useSetPaused,
} from "../api/opsQueries";
import { failureKey, type Failure } from "../lib/failure";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import { FailureNotice } from "./parts";
import { PersonalRunnersView } from "./PersonalRunnersView";

/** Личные раннеры людей: список, пауза и отзыв (смена токена только у хозяина). */
export const PersonalRunners = () => {
  const { t } = useTranslation("adminOps");
  const runners = usePersonalRunners();
  const enabled = usePersonalRunnersEnabled();
  const pause = useSetPaused();
  const revoke = useRevokeRunner();
  const now = useNow();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Failure | null>(null);
  const [revoking, setRevoking] = useState<AdminRunner | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  return (
    <>
      {notice && <FailureNotice failure={notice} />}
      <PersonalRunnersView
        status={statusOf(runners)}
        runners={runners.data ?? []}
        enabled={enabled.data}
        now={now}
        busyId={busyId}
        onRetry={() => void runners.refetch()}
        onTogglePause={(runner) => {
          setBusyId(runner.id);
          setNotice(null);
          pause.mutate(
            { id: runner.id, paused: !runner.paused },
            {
              onError: (error) => {
                setNotice({ code: failureCode(error) });
              },
              onSettled: () => {
                setBusyId(null);
              },
            },
          );
        }}
        onRevoke={(runner) => {
          setFailure(null);
          setRevoking(runner);
        }}
      />
      <ConfirmByName
        isOpen={revoking !== null}
        onClose={() => {
          setRevoking(null);
          setFailure(null);
        }}
        name={revoking?.name ?? ""}
        title={t("personal.revokeTitle")}
        description={t("personal.revokeBody", {
          name: revoking?.name ?? "",
          owner: revoking?.owner?.name ?? t("personal.unknownOwner"),
        })}
        confirmLabel={t("personal.revokeConfirm")}
        pending={revoke.isPending}
        error={failure ? t(failureKey(failure.code)) : null}
        onConfirm={() => {
          if (!revoking) return;
          setFailure(null);
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              setRevoking(null);
            },
            onError: (error) => {
              setFailure({ code: failureCode(error) });
            },
          });
        }}
      />
    </>
  );
};
