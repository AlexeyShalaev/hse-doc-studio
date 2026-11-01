import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { useServerList } from "@shared/lib";
import { ConfirmByName } from "@shared/ui";
import type {
  AdminRunner,
  AdminRunnerRotated,
  AdminRunnerToken,
  AdminRunnerTokenCreated,
} from "@entities/session";
import { opsApi } from "../api/opsApi";
import {
  opsKeys,
  POLL_MS,
  useCreateToken,
  useQueueSummary,
  useRevokeRunner,
  useRevokeToken,
  useRotateToken,
  useRunnerSummary,
  useRunningJobs,
  useSetPaused,
} from "../api/opsQueries";
import { failureKey, type Failure } from "../lib/failure";
import { busySlots } from "../lib/jobs";
import { listView, useRunnerListState, useTokenListState } from "../lib/lists";
import { RUNNER_STATUSES } from "../lib/runnerStatus";
import { useNow } from "../lib/useNow";
import { statusOf } from "../lib/viewStatus";
import {
  ConfirmDialog,
  CreateTokenDialog,
  RotatedDialog,
} from "./RunnerDialogs";
import { FailureNotice } from "./parts";
import { PersonalRunners } from "./PersonalRunners";
import { RunnersView } from "./RunnersView";

/** Раннеры: список, пауза, ротация и отзыв токена, токены регистрации. */

const LIVE_STATUSES = RUNNER_STATUSES.filter((s) => s !== "revoked");
export const Runners = ({
  creating,
  onCreatingChange,
  onOpenQueue,
}: {
  /** Открыт диалог создания токена (кнопка в заголовке раздела). */
  creating: boolean;
  onCreatingChange: (open: boolean) => void;
  onOpenQueue?: () => void;
}) => {
  const { t } = useTranslation("adminOps");
  const runnerState = useRunnerListState();
  const tokenState = useTokenListState();
  // Раннеры, токены и счётчики читаются с сервера страницей: поиск, фильтры
  // и порядок считает сервер, на клиент приходит только видимое окно.
  const runners = useServerList({
    state: runnerState,
    queryKey: opsKeys.runners,
    // Без фильтра состояния удалённые раннеры не показываются: таблица
    // сходится с числом на вкладке и в сводке. Их открывает фильтр «Удалён».
    // Личные раннеры людей здесь не показываются: у них свой раздел ниже.
    fetchPage: (params, signal) =>
      opsApi.runners(
        {
          ...(params.status ? params : { ...params, status: LIVE_STATUSES }),
          owner_kind: "instance",
        },
        signal,
      ),
    refetchInterval: POLL_MS * 3,
  });
  const tokens = useServerList({
    state: tokenState,
    queryKey: opsKeys.tokens,
    fetchPage: (params, signal) => opsApi.tokens(params, signal),
  });
  const counts = useRunnerSummary();
  const summary = useQueueSummary();
  const running = useRunningJobs();
  const now = useNow();
  const slots = useMemo(
    () => (running.data ? busySlots(running.data) : null),
    [running.data],
  );

  const pause = useSetPaused();
  const rotate = useRotateToken();
  const revoke = useRevokeRunner();
  const createToken = useCreateToken();
  const revokeToken = useRevokeToken();

  const [rotating, setRotating] = useState<AdminRunner | null>(null);
  const [rotated, setRotated] = useState<AdminRunnerRotated | null>(null);
  const [revoking, setRevoking] = useState<AdminRunner | null>(null);
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
    onCreatingChange(false);
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
        runners={listView(runners, runnerState)}
        tokens={listView(tokens, tokenState)}
        counts={counts.data ?? null}
        countsStatus={statusOf(counts)}
        summary={summary.data ?? null}
        summaryStatus={statusOf(summary)}
        slots={slots}
        now={now}
        busyId={busyId}
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
          onCreatingChange(true);
        }}
        onOpenQueue={onOpenQueue}
        onRevokeToken={(token) => {
          setFailure(null);
          setRevokingToken(token);
        }}
      />
      <div style={{ marginTop: 20 }}>
        <PersonalRunners />
      </div>
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
