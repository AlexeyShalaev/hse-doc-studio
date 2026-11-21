import { useEffect, useMemo, type ReactNode } from "react";
import {
  CalendarDays,
  ClipboardList,
  FileText,
  PenLine,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText, type PackOutcome } from "@entities/pack-studio";
import { EmptyState, ErrorState } from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import { useSituationDelta } from "../situation/useSituationDelta";
import { DocumentsBody } from "./DocumentsPart";
import { PartShell } from "./PartShell";
import { DeltaContext } from "./rows";
import {
  DataBody,
  DeadlinesBody,
  PeopleBody,
  SignaturesBody,
} from "./ProjectParts";
import {
  PART_IDS,
  countResult,
  headline,
  leadLine,
  partOfKey,
  partSummary,
  type PartId,
} from "./model";
import { partDomId, useParts } from "./partsStore";
import { makeReasoner } from "./reasons";
import { useResultData, type ResultData } from "./useResultData";
import "./space-result.css";

const ICONS: Record<PartId, ReactNode> = {
  documents: <FileText size="1rem" />,
  data: <ClipboardList size="1rem" />,
  people: <Users size="1rem" />,
  deadlines: <CalendarDays size="1rem" />,
  signatures: <PenLine size="1rem" />,
};

/**
 * Текущая часть по прокрутке: следим за верхней полосой окна. Берём первую часть, которая в неё
 * попала. Нет `IntersectionObserver` (старые окружения, тесты): текущая остаётся прежней.
 */
const useScrollSpy = (setCurrent: (part: PartId) => void, enabled: boolean) => {
  useEffect(() => {
    if (!enabled || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const inBand = new Set<PartId>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const part = PART_IDS.find((id) => partDomId(id) === entry.target.id);
          if (!part) continue;
          if (entry.isIntersecting) inBand.add(part);
          else inBand.delete(part);
        }
        const first = PART_IDS.find((id) => inBand.has(id));
        if (first) setCurrent(first);
      },
      { rootMargin: "-170px 0px -55% 0px" },
    );
    for (const id of PART_IDS) {
      const element = document.getElementById(partDomId(id));
      if (element) observer.observe(element);
    }
    return () => {
      observer.disconnect();
    };
  }, [enabled, setCurrent]);
};

const Skeleton = () => (
  <div
    className="sp-result-skeleton"
    aria-hidden="true"
    data-testid="sp-result-loading"
  >
    <span className="shimmer sp-skel-title" />
    <span className="shimmer sp-skel-line" />
    <span className="shimmer sp-skel-block" />
    <span className="shimmer sp-skel-block" />
  </div>
);

const Parts = ({
  outcome,
  data,
}: {
  outcome: PackOutcome;
  data: ResultData;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const parts = useParts();
  const counts = useMemo(() => countResult(outcome), [outcome]);
  const reasoner = useMemo(
    () => makeReasoner(t, i18n.language, outcome, data.inputs),
    [t, i18n.language, outcome, data.inputs],
  );
  const delta = useSituationDelta();
  useScrollSpy(parts.setCurrent, true);
  const rowDelta = useMemo(
    () => ({
      changed: delta.changed,
      highlight: delta.highlight,
      onlyChanged: delta.onlyChanged,
    }),
    [delta.changed, delta.highlight, delta.onlyChanged],
  );
  // «Только изменившееся»: части без изменений не показываем вовсе.
  const touched = new Set(
    [...delta.changed.keys()].map((key) => partOfKey(key)),
  );
  const body = (id: PartId): ReactNode => {
    switch (id) {
      case "documents":
        return (
          <DocumentsBody
            outcome={outcome}
            inputs={data.inputs}
            reasoner={reasoner}
          />
        );
      case "data":
        return <DataBody outcome={outcome} reasoner={reasoner} />;
      case "people":
        return <PeopleBody outcome={outcome} reasoner={reasoner} />;
      case "deadlines":
        return <DeadlinesBody outcome={outcome} reasoner={reasoner} />;
      case "signatures":
        return <SignaturesBody outcome={outcome} reasoner={reasoner} />;
    }
  };
  return (
    <DeltaContext.Provider value={rowDelta}>
      <div
        className="sp-parts"
        role="group"
        aria-label={t("result.sections")}
        aria-busy={data.calculating || undefined}
        data-stale={data.stale ? "true" : undefined}
      >
        {PART_IDS.filter((id) => !delta.onlyChanged || touched.has(id)).map(
          (id) => (
            <PartShell
              key={id}
              id={id}
              icon={ICONS[id]}
              title={t(`result.parts.${id}`)}
              summary={partSummary(t, i18n.language, outcome, counts, id)}
              open={parts.open.has(id)}
              onToggle={() => {
                parts.toggle(id);
              }}
            >
              {body(id)}
            </PartShell>
          ),
        )}
      </div>
    </DeltaContext.Provider>
  );
};

/**
 * Центр «Результата» на языке студента (pack-studio-ux.md, 5.3): заголовок «Студент получит N
 * документов», под ним части результата. Режимов «Автор» и «Как студент» нет: причины и правила
 * показывает правая колонка по выбору строки.
 */
const ResultMain = () => {
  const { t, i18n } = useTranslation("packSpace");
  const { version } = useSpace();
  const data = useResultData();
  const { outcome } = data;
  const counts = useMemo(
    () => (outcome ? countResult(outcome) : null),
    [outcome],
  );

  if (version === undefined) return null;
  if (!outcome) {
    return data.failed ? (
      <div className="sp-result" data-testid="sp-result">
        <ErrorState
          framed
          title={t("result.failedTitle")}
          description={packErrorText(data.error)}
          onRetry={data.retry}
          testId="sp-result-error"
        />
      </div>
    ) : (
      <div className="sp-result" data-testid="sp-result">
        <Skeleton />
      </div>
    );
  }
  const none = outcome.documents.length === 0;
  const status = data.calculating
    ? t(data.slow ? "result.calculatingSlow" : "result.calculating")
    : "";
  return (
    <div className="sp-result" data-testid="sp-result" lang={i18n.language}>
      <header className="sp-result-head">
        <h2 className="sp-result-title" data-testid="sp-result-title">
          {counts ? headline(t, counts) : null}
        </h2>
        <p className="sp-result-lead">
          {counts ? `${leadLine(t, counts)} ` : null}
          <span className="sp-result-note">{t("result.leadNote")}</span>
        </p>
        <p
          className="sp-result-status"
          role="status"
          aria-live="polite"
          data-testid="sp-result-status"
        >
          {status}
        </p>
      </header>
      {data.failed ? (
        <div className="sp-banner" role="alert" data-testid="sp-result-stale">
          <span>
            <strong>{t("result.failedTitle")}.</strong>{" "}
            {t("result.failedStale")} {packErrorText(data.error)}
          </span>
          <button type="button" className="btn sm" onClick={data.retry}>
            {t("result.retry")}
          </button>
        </div>
      ) : null}
      {none ? (
        <EmptyState
          framed
          icon={<FileText size="1.5rem" />}
          title={t("result.emptyTitle")}
          description={t("result.emptyLead")}
          testId="sp-result-empty"
        />
      ) : (
        <Parts outcome={outcome} data={data} />
      )}
    </div>
  );
};

export default ResultMain;
