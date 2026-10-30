import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { ConfirmByName } from "@shared/ui";
import type {
  AdminRunner,
  AdminRunnerRotated,
  AdminRunnerToken,
  AdminRunnerTokenCreated,
} from "@entities/session";
import {
  useCreateToken,
  useRevokeRunner,
  useRevokeToken,
  useRotateToken,
  useRunners,
  useSetPaused,
  useTokens,
} from "../api/opsQueries";
import { failureKey, type Failure } from "../lib/failure";
import { useNow } from "../lib/useNow";
import {
  ConfirmDialog,
  CreateTokenDialog,
  RotatedDialog,
} from "./RunnerDialogs";
import { FailureNotice } from "./parts";
import { RunnersView } from "./RunnersView";

const statusOf = (q: { isError: boolean; isPending: boolean }) =>
  q.isError ? "error" : q.isPending ? "loading" : "ready";

/** Раннеры: список, пауза, ротация и отзыв токена, токены регистрации. */
export const Runners = ({
  initialCreateToken = false,
}: {
  /** Открыть создание токена сразу (ссылка со сводки). */
  initialCreateToken?: boolean;
}) => {
  const { t } = useTranslation("adminOps");
  const runners = useRunners();
  const tokens = useTokens();
  const now = useNow();

  const pause = useSetPaused();
  const rotate = useRotateToken();
  const revoke = useRevokeRunner();
  const createToken = useCreateToken();
  const revokeToken = useRevokeToken();

  const [rotating, setRotating] = useState<AdminRunner | null>(null);
  const [rotated, setRotated] = useState<AdminRunnerRotated | null>(null);
  const [revoking, setRevoking] = useState<AdminRunner | null>(null);
  const [creating, setCreating] = useState(initialCreateToken);
  const [created, setCreated] = useState<AdminRunnerTokenCreated | null>(null);
  const [revokingToken, setRevokingToken] = useState<AdminRunnerToken | null>(
    null,
  );
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<Failure | null>(null);

  const fail = (error: unknown) => {
    setFailure({ code: failureCode(error) });
  };
  const closeCreate = () => {
    setCreating(false);
    setCreated(null);
    setFailure(null);
    createToken.reset();
  };

  return (
    <>
      {notice && (
        <div style={{ marginBottom: 12 }}>
          <FailureNotice failure={notice} />
        </div>
      )}
      <RunnersView
        status={statusOf(runners)}
        runners={runners.data ?? []}
        tokensStatus={statusOf(tokens)}
        tokens={tokens.data ?? []}
        now={now}
        busyId={busyId}
        onRetry={() => void runners.refetch()}
        onRetryTokens={() => void tokens.refetch()}
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
        onRotate={(runner) => {
          setFailure(null);
          setRotating(runner);
        }}
        onRevoke={(runner) => {
          setFailure(null);
          setRevoking(runner);
        }}
        onCreateToken={() => {
          setFailure(null);
          setCreating(true);
        }}
        onRevokeToken={(token) => {
          setFailure(null);
          setRevokingToken(token);
        }}
      />
      <ConfirmDialog
        isOpen={rotating !== null}
        title={t("runners.rotateDialog.title", { name: rotating?.name ?? "" })}
        body={t("runners.rotateDialog.body")}
        confirmLabel={t("runners.rotateDialog.confirm")}
        pending={rotate.isPending}
        failure={failure}
        testId="rotate-dialog"
        onClose={() => {
          setRotating(null);
          setFailure(null);
        }}
        onConfirm={() => {
          if (!rotating) return;
          setFailure(null);
          rotate.mutate(rotating.id, {
            onSuccess: (result) => {
              setRotating(null);
              setRotated(result);
            },
            onError: fail,
          });
        }}
      />
      <RotatedDialog
        rotated={rotated}
        onClose={() => {
          setRotated(null);
          rotate.reset();
        }}
      />

      <ConfirmByName
        isOpen={revoking !== null}
        onClose={() => {
          setRevoking(null);
          setFailure(null);
        }}
        name={revoking?.name ?? ""}
        title={t("runners.revoke.title")}
        description={t("runners.revoke.body")}
        confirmLabel={t("runners.revoke.confirm")}
        pending={revoke.isPending}
        error={failure ? t(failureKey(failure.code)) : null}
        onConfirm={() => {
          if (!revoking) return;
          setFailure(null);
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              setRevoking(null);
            },
            onError: fail,
          });
        }}
      />

      <CreateTokenDialog
        isOpen={creating}
        pending={createToken.isPending}
        failure={failure}
        created={created}
        onClose={closeCreate}
        onSubmit={(body) => {
          setFailure(null);
          createToken.mutate(body, {
            onSuccess: (result) => {
              setCreated(result);
            },
            onError: fail,
          });
        }}
      />

      <ConfirmDialog
        isOpen={revokingToken !== null}
        title={t("tokens.revokeDialog.title")}
        body={t("tokens.revokeDialog.body", {
          label: revokingToken?.label
            ? revokingToken.label
            : t("tokens.noLabel"),
        })}
        confirmLabel={t("tokens.revokeDialog.confirm")}
        danger
        pending={revokeToken.isPending}
        failure={failure}
        testId="token-revoke-dialog"
        onClose={() => {
          setRevokingToken(null);
          setFailure(null);
        }}
        onConfirm={() => {
          if (!revokingToken) return;
          setFailure(null);
          revokeToken.mutate(revokingToken.id, {
            onSuccess: () => {
              setRevokingToken(null);
            },
            onError: fail,
          });
        }}
      />
    </>
  );
};
