import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { failureCode } from "@shared/api";
import { useBootstrap } from "@entities/session";
import {
  normalizeUserCode,
  useDecideRunnerPairing,
  useRunnerPairing,
  type RunnerPairingDecision,
} from "@entities/runner";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import {
  RunnerPairView,
  type PairResult,
  type RunnerPairViewState,
} from "./RunnerPairView";

/** Код ответа сервера, который сам по себе итог: 404, 410, повтор, предел, выключено. */
const RESULT_OF: Record<string, PairResult> = {
  runner_pairing_invalid: "invalid",
  not_found: "invalid",
  runner_pairing_expired: "expired",
  runner_pairing_used: "used",
  personal_runners_disabled: "disabled",
  personal_runner_limit: "limit",
};

const COUNTDOWN_MS = 1000;

const useTick = (): number => {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, COUNTDOWN_MS);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  return now;
};

/**
 * Страница подтверждения сопряжения (/settings/runners/pair?code=…): человек
 * видит, какое устройство просит доступ, и подключает его как свой раннер.
 */
export const RunnerPairPage = () => {
  const [params, setParams] = useSearchParams();
  const raw = params.get("code");
  const code = raw === null ? null : normalizeUserCode(raw);
  const pairing = useRunnerPairing(code);
  const decide = useDecideRunnerPairing();
  const [decided, setDecided] = useState<PairResult | null>(null);
  const [deciding, setDeciding] = useState<RunnerPairingDecision | null>(null);
  const now = useTick();
  const enabled = useBootstrap().data?.capabilities.personal_runners !== false;

  const state = ((): RunnerPairViewState => {
    if (raw === null) return { kind: "enter" };
    if (code === null) return { kind: "result", result: "invalid" };
    if (decided) return { kind: "result", result: decided };
    if (pairing.isError) {
      const result = RESULT_OF[failureCode(pairing.error)];
      return result ? { kind: "result", result } : { kind: "error" };
    }
    if (!pairing.data) return { kind: "loading" };
    // Код уже решён раньше (в другой вкладке или другим человеком).
    if (
      pairing.data.status === "approved" ||
      pairing.data.status === "denied"
    ) {
      return { kind: "result", result: "used", info: pairing.data };
    }
    if (pairing.data.status === "expired") {
      return { kind: "result", result: "expired", info: pairing.data };
    }
    if (!enabled) return { kind: "result", result: "disabled" };
    return { kind: "pending", info: pairing.data };
  })();

  const run = (decision: RunnerPairingDecision) => {
    if (code === null) return;
    setDeciding(decision);
    decide.mutate(
      { code, decision },
      {
        onSuccess: (info) => {
          setDecided(info.status === "denied" ? "denied" : "approved");
        },
        onError: (error) => {
          setDecided(RESULT_OF[failureCode(error)] ?? "invalid");
        },
        onSettled: () => {
          setDeciding(null);
        },
      },
    );
  };

  return (
    <div className="flex flex-col flex-1 bg-bg-0" style={{ minHeight: 0 }}>
      <AppTitlebar />
      <RunnerPairView
        state={state}
        now={now}
        deciding={deciding}
        onCode={(next) => {
          setDecided(null);
          setParams({ code: next });
        }}
        onApprove={() => {
          run("approve");
        }}
        onDeny={() => {
          run("deny");
        }}
        onRetry={() => void pairing.refetch()}
        onOtherCode={() => {
          setDecided(null);
          setParams({});
        }}
      />
      <AppStatusBar />
    </div>
  );
};
