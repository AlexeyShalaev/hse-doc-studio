import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { i18n, toast } from "@shared/lib";
import { ErrorState, Modal, Button, Spinner } from "@shared/ui";
import { useAIProviders } from "@entities/ai-provider";
import {
  useCancelRemotePairing,
  usePairRemoteRunner,
  useRemoteRunner,
  useRemoteRunnerToken,
  useUnpairRemoteRunner,
  useUpdateRemoteRunner,
  type UpdateRemoteRunnerRequest,
} from "@entities/runner";
import { cloudCandidates } from "../lib/candidates";
import { RemoteRunnerView } from "./RemoteRunnerView";

const NO_CHANGE: UpdateRemoteRunnerRequest = {
  enabled: null,
  server_url: null,
  name: null,
  concurrency: null,
  yield_to_local: null,
  ai_endpoints: null,
};

const textOf = (code: string): string => {
  const key = `errors:code.${code}`;
  return i18n.exists(key)
    ? i18n.t(key)
    : i18n.t(
        code === "network"
          ? "runners:failure.network"
          : "runners:failure.unknown",
      );
};

const TICK_MS = 1000;

/** Раздел настроек «Облачные сборки» локальной Студии. */
export const RemoteRunnerSection = () => {
  const { t } = useTranslation("runners");
  const remote = useRemoteRunner();
  const providers = useAIProviders();
  const update = useUpdateRemoteRunner();
  const pair = usePairRemoteRunner();
  const token = useRemoteRunnerToken();
  const cancel = useCancelRemotePairing();
  const unpair = useUnpairRemoteRunner();
  const [error, setError] = useState<string | null>(null);
  const [confirmUnpair, setConfirmUnpair] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // Обратный отсчёт кода сопряжения: тикаем, только пока код на экране.
  const pairing = remote.data?.state === "pairing";
  useEffect(() => {
    if (!pairing) return undefined;
    const id = window.setInterval(() => {
      setNow(Date.now());
    }, TICK_MS);
    return () => {
      window.clearInterval(id);
    };
  }, [pairing]);

  const busy =
    update.isPending ||
    pair.isPending ||
    token.isPending ||
    cancel.isPending ||
    unpair.isPending;
  const fail = (e: unknown) => {
    setError(textOf(failureCode(e)));
  };
  const patch = (body: Partial<UpdateRemoteRunnerRequest>) => {
    setError(null);
    update.mutate({ ...NO_CHANGE, ...body }, { onError: fail });
  };

  if (!remote.data) {
    return remote.isError ? (
      <ErrorState
        framed
        onRetry={() => void remote.refetch()}
        testId="remote-runner-error"
      />
    ) : (
      <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
        <Spinner size="sm" />
      </div>
    );
  }

  return (
    <>
      <RemoteRunnerView
        status={remote.data}
        candidates={cloudCandidates(providers.data ?? [])}
        now={now}
        busy={busy}
        error={error}
        detailText={
          remote.data.detail_code ? textOf(remote.data.detail_code) : null
        }
        onToggle={(enabled) => {
          patch({ enabled });
        }}
        onPair={(serverUrl, name) => {
          setError(null);
          pair.mutate({ serverUrl, name }, { onError: fail });
        }}
        onToken={(serverUrl, value) => {
          setError(null);
          token.mutate({ serverUrl, token: value }, { onError: fail });
        }}
        onCancelPairing={() => {
          setError(null);
          cancel.mutate(undefined, { onError: fail });
        }}
        onUnpair={() => {
          setConfirmUnpair(true);
        }}
        onConcurrency={(concurrency) => {
          patch({ concurrency });
        }}
        onYield={(value) => {
          patch({ yield_to_local: value });
        }}
        onModels={(choices) => {
          patch({ ai_endpoints: choices });
        }}
      />
      <Modal
        isOpen={confirmUnpair}
        onClose={() => {
          setConfirmUnpair(false);
        }}
        title={t("remote.unpairTitle")}
        description={t("remote.unpairBody")}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirmUnpair(false);
              }}
            >
              {t("cancel")}
            </Button>
            <Button
              type="button"
              variant="danger"
              disabled={unpair.isPending}
              data-testid="remote-runner-unpair-confirm"
              onClick={() => {
                unpair.mutate(undefined, {
                  onSuccess: () => {
                    setConfirmUnpair(false);
                    toast.success(t("remote.unpaired"));
                  },
                  onError: (e) => {
                    setConfirmUnpair(false);
                    fail(e);
                  },
                });
              }}
            >
              {t("remote.unpairConfirm")}
            </Button>
          </>
        }
      />
    </>
  );
};
