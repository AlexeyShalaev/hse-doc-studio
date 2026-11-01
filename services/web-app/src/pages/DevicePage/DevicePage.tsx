import { useState } from "react";
import { useSearchParams } from "react-router";
import { failureCode } from "@shared/api";
import { normalizeDeviceCode, useNowTick } from "@shared/ui/DeviceCodeCard";
import {
  useDecideDevice,
  useDeviceAuthorization,
  type GitScope,
} from "@entities/git-server";
import { AppStatusBar } from "@widgets/AppStatusBar";
import { AppTitlebar } from "@widgets/AppTitlebar";
import {
  DeviceView,
  type DeviceResultKind,
  type DeviceViewState,
} from "./DeviceView";

/** Код ответа сервера, который сам по себе итог. */
const RESULT_OF: Record<string, DeviceResultKind> = {
  device_code_invalid: "invalid",
  not_found: "invalid",
  device_code_expired: "expired",
  device_code_used: "used",
};

/**
 * Страница /device?code=…: человек подтверждает вход Студии на компьютере в
 * git этого сервера и выбирает права. Работает только по сессии: гостя шлюз
 * уводит на вход и возвращает сюда с тем же кодом.
 */
export const DevicePage = () => {
  const [params, setParams] = useSearchParams();
  const raw = params.get("code");
  const code = raw === null ? null : normalizeDeviceCode(raw);
  const info = useDeviceAuthorization(code);
  const decide = useDecideDevice();
  const [decided, setDecided] = useState<DeviceResultKind | null>(null);
  const [deciding, setDeciding] = useState<"approve" | "deny" | null>(null);
  const now = useNowTick();

  const state = ((): DeviceViewState => {
    if (raw === null) return { kind: "enter" };
    if (code === null) return { kind: "result", result: "invalid" };
    if (decided) return { kind: "result", result: decided };
    if (info.isError) {
      const result = RESULT_OF[failureCode(info.error)];
      return result ? { kind: "result", result } : { kind: "error" };
    }
    if (!info.data) return { kind: "loading" };
    const status = info.data.status;
    if (status === "approved" || status === "denied" || status === "delivered")
      return { kind: "result", result: "used" };
    if (status === "expired") return { kind: "result", result: "expired" };
    return { kind: "pending", info: info.data };
  })();

  const run = (decision: "approve" | "deny", scopes: GitScope[]) => {
    if (code === null) return;
    setDeciding(decision);
    decide.mutate(
      { code, body: { decision, scopes } },
      {
        onSuccess: (result) => {
          setDecided(result.status === "denied" ? "denied" : "approved");
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
      <DeviceView
        state={state}
        now={now}
        deciding={deciding}
        onCode={(next) => {
          setDecided(null);
          setParams({ code: next });
        }}
        onApprove={(scopes) => {
          run("approve", scopes);
        }}
        onDeny={() => {
          run("deny", []);
        }}
        onRetry={() => void info.refetch()}
        onOtherCode={() => {
          setDecided(null);
          setParams({});
        }}
      />
      <AppStatusBar />
    </div>
  );
};
