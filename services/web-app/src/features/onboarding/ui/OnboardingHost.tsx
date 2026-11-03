import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";
import { useOnboardingState } from "@entities/onboarding";
import {
  INVITE_DISMISSED_KEY,
  decidePrompt,
  readAutostartEnv,
} from "../lib/autostart";
import { useOnboardingStore } from "../model/onboardingStore";
import { useOnboardingAvailable } from "../model/useOnboardingProgress";
import { InviteCard } from "./InviteCard";

// Анкета, экскурсия и итог грузятся отдельным чанком, только когда тур нужен.
const OnboardingFlow = lazy(() =>
  import("./flow/OnboardingFlow").then((m) => ({ default: m.OnboardingFlow })),
);

const readDismissed = (): boolean => {
  try {
    return window.localStorage.getItem(INVITE_DISMISSED_KEY) !== null;
  } catch {
    return false;
  }
};

/**
 * Точка входа онбординга в оболочке приложения: сам открывает тур новичку на
 * главной, давнему пользователю показывает приглашение, и держит ленивый чанк
 * тура, пока он идёт.
 */
export const OnboardingHost = () => {
  const available = useOnboardingAvailable();
  const { pathname } = useLocation();
  const { data: state } = useOnboardingState({ enabled: available });
  const phase = useOnboardingStore((s) => s.phase);
  const start = useOnboardingStore((s) => s.start);
  const [dismissed, setDismissed] = useState(readDismissed);
  const autostarted = useRef(false);

  const prompt = available
    ? decidePrompt(state, readAutostartEnv(pathname), dismissed)
    : "none";

  useEffect(() => {
    if (prompt !== "autostart" || autostarted.current || phase !== "idle") {
      return;
    }
    autostarted.current = true;
    start("auto", state?.answers);
  }, [prompt, phase, start, state?.answers]);

  const dismiss = () => {
    try {
      window.localStorage.setItem(
        INVITE_DISMISSED_KEY,
        new Date().toISOString(),
      );
    } catch {
      // приватный режим: приглашение просто вернётся после перезагрузки
    }
    setDismissed(true);
  };

  const flowVisible =
    phase === "intro" || phase === "interface" || phase === "finish";

  return (
    <>
      {flowVisible && (
        <Suspense fallback={null}>
          <OnboardingFlow />
        </Suspense>
      )}
      {prompt === "invite" && phase === "idle" && (
        <InviteCard
          onStart={() => {
            dismiss();
            start("manual", state?.answers);
          }}
          onDismiss={dismiss}
        />
      )}
    </>
  );
};
