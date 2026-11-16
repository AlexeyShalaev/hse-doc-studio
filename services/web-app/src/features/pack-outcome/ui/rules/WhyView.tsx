import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  busyDelaySeconds,
  isElementGone,
  isOutcomeBusy,
  packErrorText,
  type OutcomeElementRef,
} from "@entities/pack-studio";
import { Spinner } from "@shared/ui";
import { describeElement } from "../../lib/elements";
import { makeTraceText } from "../../lib/explain";
import { useApplyInput, useRestoreInput } from "../../lib/applyInput";
import { useOutcomePart } from "../../lib/part";
import { useOutcomeModel } from "../../model";
import { Notice } from "../Notice";
import { Chain } from "./Chain";
import { Readers } from "./Readers";
import { ElementState } from "./StateChip";
import { WhatIf, type AppliedWhatIf } from "./WhatIf";
import { useWhy } from "./useWhy";

type WhyViewProps = {
  element: OutcomeElementRef;
  applied: AppliedWhatIf | null;
  onApplied: (next: AppliedWhatIf | null) => void;
};

/** «Сервер занят, повторю через N секунд» с обратным отсчётом. */
const BusyWait = ({ seconds }: { seconds: number }) => {
  const { t } = useTranslation("packOutcome");
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    if (seconds <= 0) return undefined;
    const timer = setInterval(() => {
      setLeft((n) => Math.max(0, n - 1));
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [seconds]);
  return (
    <p className="po-note" role="status" data-testid="outcome-why-busy">
      {t("rules.busy", { count: left })}
    </p>
  );
};

const Skeleton = () => (
  <div
    className="po-skeleton"
    aria-hidden="true"
    data-testid="outcome-why-loading"
  >
    <div className="shimmer po-skeleton-row" />
    <div className="shimmer po-skeleton-row" data-short="true" />
    <div className="shimmer po-skeleton-row" />
    <div className="shimmer po-skeleton-row" data-short="true" />
  </div>
);

/**
 * «Почему?» выбранного элемента (template-studio-outcome.md, 3.5): заголовок и состояние,
 * цепочка правил, соседи по правилам, «что если». Всё из ответа `explain`; клиент ничего не
 * считает. При пересчёте прежний ответ того же элемента остаётся приглушённым.
 */
export const WhyView = ({ element, applied, onApplied }: WhyViewProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { shown, inputs, request, phone } = useOutcomeModel();
  const { query } = useWhy(element);
  const apply = useApplyInput();
  const restore = useRestoreInput();
  const data = query.data;
  // Названия правил проверок приходят отдельной частью результата: она нужна, только если выбрано правило.
  const checks = useOutcomePart("checks", element.section === "checks");
  const named = useMemo(
    () => (shown && checks.items ? { ...shown, checks: checks.items } : shown),
    [shown, checks.items],
  );
  const info = describeElement(named, element, i18n.language);
  const list = inputs.data?.inputs;
  const text = useMemo(
    () => makeTraceText(t, i18n.language, list),
    [t, i18n.language, list],
  );
  const refreshing =
    data !== undefined && (query.isPlaceholderData || query.isFetching);
  const title =
    info.kind === "route_step"
      ? t("rules.stepTitle", { n: info.step ?? 0, point: info.point ?? "" })
      : info.title;

  const busy = isOutcomeBusy(query.error);
  const failed = query.isError && !isElementGone(query.error);
  // Занятый сервер: секунды до повтора, чтобы автор видел, что экран не завис.
  const retrying =
    query.failureCount > 0 &&
    query.isFetching &&
    isOutcomeBusy(query.failureReason);

  const announce = data
    ? t("rules.announce.loaded", { title })
    : failed
      ? t("rules.announce.failed")
      : "";

  return (
    <div
      className="po-why"
      data-stale={refreshing ? "true" : undefined}
      aria-busy={query.isPending || refreshing}
      data-testid="outcome-why"
    >
      <header className="po-why-head">
        <p className="po-rules-label">
          <span className="po-mark">{t(`sections.${element.section}`)}</span>
          <span>{t(`rules.kind.${info.kind}`)}</span>
          {info.point && info.kind !== "point" && info.kind !== "route" && (
            <span>{t("rules.inPoint", { point: info.point })}</span>
          )}
        </p>
        <h3 className="po-why-title" data-testid="outcome-why-title">
          {title}
        </h3>
        <p className="po-why-meta">
          <span className="mono po-rules-id" data-testid="outcome-selected">
            {element.id}
          </span>
          {data && (
            <ElementState state={data.state} testId="outcome-why-state" />
          )}
        </p>
      </header>

      {refreshing && (
        <p className="po-why-busy" data-testid="outcome-why-refreshing">
          <Spinner size="sm" />
          {t("status.recalculating")}
        </p>
      )}

      {query.isPending && !failed && <Skeleton />}

      {retrying && (
        <BusyWait
          key={query.failureCount}
          seconds={busyDelaySeconds(query.failureReason)}
        />
      )}

      {failed && (
        <Notice
          tone="error"
          title={t(busy ? "rules.busyFailed" : "rules.failed")}
          testId="outcome-why-error"
          actions={
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-why-retry"
              onClick={() => void query.refetch()}
            >
              {t("status.retry")}
            </button>
          }
        >
          {packErrorText(query.error)}
        </Notice>
      )}

      {data && (
        <>
          {info.kind === "route_step" && (
            <p className="po-note" data-testid="outcome-why-step-note">
              {t("rules.stepNote")}
            </p>
          )}
          {data.chain.length > 0 ? (
            <section
              aria-labelledby="po-chain-title"
              className="po-rules-block"
            >
              <h3 className="po-rules-sub" id="po-chain-title">
                {t("rules.chain.title")}
                <span className="po-group-count">{data.chain.length}</span>
              </h3>
              <Chain chain={data.chain} text={text} phone={phone} />
            </section>
          ) : (
            <section
              className="po-rules-block"
              data-testid="outcome-chain-empty"
            >
              <h3 className="po-rules-sub">{t("rules.chain.title")}</h3>
              <p className="po-calm">{t("rules.chain.empty")}</p>
              <p className="po-note">
                {t(
                  data.counterfactuals.length > 0
                    ? "rules.chain.emptyDepends"
                    : "rules.chain.emptyStatic",
                )}
              </p>
            </section>
          )}
          <Readers readers={data.readers} outcome={named} />
          <WhatIf
            counterfactuals={data.counterfactuals}
            text={text}
            outcome={shown}
            applied={applied}
            onApply={(input, value) => {
              onApplied({ input, value, previous: request.inputs?.[input] });
              apply(input, value);
            }}
            onRestore={() => {
              if (applied) restore(applied.input, applied.previous);
              onApplied(null);
            }}
          />
        </>
      )}

      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="outcome-why-live"
      >
        {announce}
      </div>
    </div>
  );
};
