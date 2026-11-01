import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { ConfirmByName } from "@shared/ui";
import { useBootstrap } from "@entities/session";
import {
  useCreateMyRunnerToken,
  useMyRunnerTokens,
  useMyRunners,
  useRevokeMyRunner,
  useRevokeMyRunnerToken,
  useRotateMyRunner,
  useUpdateMyRunner,
  type MyRunner,
  type MyRunnerRotated,
  type MyRunnerToken,
  type MyRunnerTokenCreated,
} from "@entities/runner";
import { useFailureText } from "../lib/failure";
import { useNow } from "../lib/useNow";
import { ConnectRunnerDialog } from "./ConnectRunnerDialog";
import { MyRunnersView } from "./MyRunnersView";
import {
  ConfirmDialog,
  ReconnectDialog,
  RenameDialog,
  RotatedDialog,
} from "./RunnerDialogs";

/** Раздел настроек «Мои раннеры» серверного режима: данные, действия и диалоги. */
export const MyRunnersSection = () => {
  const { t } = useTranslation("runners");
  const navigate = useNavigate();
  const failureText = useFailureText();
  const bootstrap = useBootstrap().data;
  const enabled = bootstrap?.capabilities.personal_runners === true;
  const [connecting, setConnecting] = useState(false);
  const runners = useMyRunners({ fastPoll: connecting });
  const tokens = useMyRunnerTokens();
  const update = useUpdateMyRunner();
  const rotate = useRotateMyRunner();
  const revoke = useRevokeMyRunner();
  const createToken = useCreateMyRunnerToken();
  const revokeToken = useRevokeMyRunnerToken();
  const now = useNow();

  const [created, setCreated] = useState<MyRunnerTokenCreated | null>(null);
  const [renaming, setRenaming] = useState<MyRunner | null>(null);
  const [rotating, setRotating] = useState<MyRunner | null>(null);
  const [rotated, setRotated] = useState<MyRunnerRotated | null>(null);
  const [reconnecting, setReconnecting] = useState<MyRunner | null>(null);
  const [revoking, setRevoking] = useState<MyRunner | null>(null);
  const [revokingToken, setRevokingToken] = useState<MyRunnerToken | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const fail = (e: unknown) => {
    setError(failureText(failureCode(e)));
  };

  // Пока открыт диалог подключения, новый раннер в списке значит «подключился»:
  // говорим об этом тостом, не дожидаясь, пока человек закроет окно.
  const known = useRef<Set<string> | null>(null);
  const list = runners.data;
  const refetchTokens = tokens.refetch;
  useEffect(() => {
    if (!connecting) {
      known.current = null;
      return;
    }
    if (!list) return;
    if (known.current === null) {
      known.current = new Set(list.map((r) => r.id));
      return;
    }
    for (const runner of list) {
      if (!known.current.has(runner.id)) {
        known.current.add(runner.id);
        toast.success(t("mine.connected", { name: runner.name }));
        // Раннер израсходовал токен: из «Неиспользованных» он должен уйти сразу.
        void refetchTokens();
      }
    }
  }, [connecting, list, t, refetchTokens]);

  const closeConnect = () => {
    // Раннер мог подключиться между опросами: после закрытия диалога список
    // и токены перечитываются сразу, а не через полминуты.
    void runners.refetch();
    void tokens.refetch();
    setConnecting(false);
    setCreated(null);
    setError(null);
    createToken.reset();
  };

  return (
    <>
      <MyRunnersView
        status={runners.data ? "ready" : runners.isError ? "error" : "loading"}
        runners={runners.data ?? []}
        tokens={tokens.data ?? []}
        enabled={enabled}
        serverVersion={bootstrap?.version ?? ""}
        now={now}
        busyId={busyId}
        onRetry={() => void runners.refetch()}
        onConnect={() => {
          setError(null);
          setConnecting(true);
        }}
        onRename={(runner) => {
          setError(null);
          setRenaming(runner);
        }}
        onTogglePause={(runner) => {
          setBusyId(runner.id);
          update.mutate(
            { id: runner.id, body: { name: null, paused: !runner.paused } },
            {
              onSuccess: (next) => {
                toast.success(
                  next.paused
                    ? t("mine.paused", { name: next.name })
                    : t("mine.resumed", { name: next.name }),
                );
              },
              onError: (e) => {
                toast.error(failureText(failureCode(e)));
              },
              onSettled: () => {
                setBusyId(null);
              },
            },
          );
        }}
        onRotate={(runner) => {
          setError(null);
          setRotating(runner);
        }}
        onReconnect={setReconnecting}
        onRevoke={(runner) => {
          setError(null);
          setRevoking(runner);
        }}
        onRevokeToken={(token) => {
          setError(null);
          setRevokingToken(token);
        }}
      />

      <ConnectRunnerDialog
        isOpen={connecting}
        pending={createToken.isPending}
        error={error}
        created={created}
        onClose={closeConnect}
        onPairCode={(code) => {
          closeConnect();
          void navigate(
            `/settings/runners/pair?code=${encodeURIComponent(code)}`,
          );
        }}
        onCreateToken={(body) => {
          setError(null);
          createToken.mutate(body, {
            onSuccess: setCreated,
            onError: fail,
          });
        }}
      />

      <RenameDialog
        runner={renaming}
        pending={update.isPending}
        error={error}
        onClose={() => {
          setRenaming(null);
          setError(null);
        }}
        onSave={(name) => {
          if (!renaming) return;
          setError(null);
          update.mutate(
            { id: renaming.id, body: { name, paused: null } },
            {
              onSuccess: () => {
                setRenaming(null);
                toast.success(t("mine.renamed"));
              },
              onError: fail,
            },
          );
        }}
      />

      <ConfirmDialog
        isOpen={rotating !== null}
        title={t("rotate.confirmTitle", { name: rotating?.name ?? "" })}
        body={t("rotate.confirmBody")}
        confirmLabel={t("rotate.confirm")}
        pending={rotate.isPending}
        error={error}
        testId="my-runner-rotate-dialog"
        onClose={() => {
          setRotating(null);
          setError(null);
        }}
        onConfirm={() => {
          if (!rotating) return;
          setError(null);
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
      <ReconnectDialog
        runner={reconnecting}
        onClose={() => {
          setReconnecting(null);
        }}
      />

      <ConfirmByName
        isOpen={revoking !== null}
        onClose={() => {
          setRevoking(null);
          setError(null);
        }}
        name={revoking?.name ?? ""}
        title={t("revoke.title")}
        description={t("revoke.body")}
        confirmLabel={t("revoke.confirm")}
        pending={revoke.isPending}
        error={error}
        onConfirm={() => {
          if (!revoking) return;
          const name = revoking.name;
          setError(null);
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              setRevoking(null);
              toast.success(t("mine.revoked", { name }));
            },
            onError: fail,
          });
        }}
      />

      <ConfirmDialog
        isOpen={revokingToken !== null}
        title={t("tokens.revokeTitle")}
        body={t("tokens.revokeBody", {
          label:
            revokingToken === null || revokingToken.label === ""
              ? t("tokens.noLabel")
              : revokingToken.label,
        })}
        confirmLabel={t("tokens.revoke")}
        danger
        pending={revokeToken.isPending}
        error={error}
        testId="my-runner-token-revoke-dialog"
        onClose={() => {
          setRevokingToken(null);
          setError(null);
        }}
        onConfirm={() => {
          if (!revokingToken) return;
          setError(null);
          revokeToken.mutate(revokingToken.id, {
            onSuccess: () => {
              setRevokingToken(null);
              toast.success(t("tokens.revoked"));
            },
            onError: fail,
          });
        }}
      />
    </>
  );
};
