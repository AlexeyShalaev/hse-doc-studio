import { useId, useState } from "react";
import { TriangleAlert } from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import type { OutcomePoint, PackOutcome } from "@entities/pack-studio";
import { Badge, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { personaLabel } from "../../lib/personas";
import {
  absentPersonas,
  emptySteps,
  isEmptyPerson,
} from "../../lib/routeSteps";
import { pairId, skippedId, stepId } from "../../lib/routeIds";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import "../../outcomeRoute.css";
import { PaleSlot } from "./PaleSlot";
import { SectionShell } from "./SectionShell";
import {
  Disclosure,
  FilterBar,
  GroupTitle,
  PickButton,
  PickItem,
  Reason,
  StepWarning,
  Stats,
} from "./parts";
import { groupBy, matches, onArrowNav } from "./helpers";
import { useDocNames } from "./useDocNames";
import { useExplain } from "./useExplain";

type Pair = OutcomePoint["route"]["pairs"][number];
type When = Pair["when"];
type Names = (id: string) => string;

/** Условие слота словами: «если руководитель из компании». Только пересказ данных сервера. */
const whenText = (t: TFunction<"packOutcome">, when: When): string | null => {
  if (!when) return null;
  const person = t(`reasons.subjects.${when.person}`, {
    defaultValue: when.person,
  });
  return when.role
    ? t("route.whenOrg", { person, org: t(`route.orgOf.${when.role}`) })
    : t("route.whenSet", { person });
};

const SourceBadge = ({ source }: { source: Pair["source"] }) => {
  const { t } = useTranslation("packOutcome");
  return (
    <Badge variant={source === "preset" ? "info" : "subtle"}>
      {t(`route.source.${source}`)}
    </Badge>
  );
};

/** Чип человека в шаге: роль и имя; пустое имя это предупреждение, а не пустое место. */
const Person = ({
  persona,
  name,
  gone,
  testId,
}: {
  persona: string;
  name: string;
  gone: boolean;
  testId: string;
}) => {
  const { t } = useTranslation("packOutcome");
  return (
    <span
      className="po-person"
      data-empty={gone ? "true" : undefined}
      data-testid={testId}
    >
      <span className="po-person-role">{personaLabel(t, persona)}</span>
      {gone ? (
        <span className="po-person-warn">
          <TriangleAlert size="0.75rem" aria-hidden="true" />
          {name.trim() === "" ? t("route.noName") : name}
          <span className="sr-only">{`: ${t("route.noPerson")}`}</span>
        </span>
      ) : (
        <span className="po-person-who">{name}</span>
      )}
    </span>
  );
};

const Step = ({
  point,
  index,
  step,
  absent,
}: {
  point: OutcomePoint;
  index: number;
  step: OutcomePoint["route"]["steps"][number];
  absent: ReadonlySet<string>;
}) => {
  const { t } = useTranslation("packOutcome");
  const n = index + 1;
  return (
    <li
      className="po-step"
      data-parallel={step.length > 1 ? "true" : undefined}
      data-testid={`outcome-step-${point.id}-${String(n)}`}
    >
      <PickButton
        el={{ section: "route", id: stepId(point.id, n) }}
        title={t("route.step", { n })}
        badges={
          step.length > 1 ? (
            <Badge variant="subtle">{t("route.parallel")}</Badge>
          ) : undefined
        }
      >
        <span className="po-persons">
          {step.map((person) => (
            <Person
              key={person.persona}
              persona={person.persona}
              name={person.name}
              gone={isEmptyPerson(person, absent)}
              testId={`outcome-route-person-${point.id}-${String(n)}-${person.persona}`}
            />
          ))}
        </span>
      </PickButton>
    </li>
  );
};

const PairCard = ({
  point,
  pair,
  names,
  who,
}: {
  point: OutcomePoint;
  pair: Pair;
  names: Names;
  who: ReadonlyMap<string, string>;
}) => {
  const { t } = useTranslation("packOutcome");
  const when = whenText(t, pair.when);
  const name = who.get(pair.persona) ?? "";
  return (
    <PickItem
      el={{
        section: "route",
        id: pairId(point.id, pair.doc_id, pair.slot_id, pair.persona),
      }}
      testId={`outcome-pair-${point.id}-${pair.doc_id}-${pair.slot_id}${pair.persona === pair.slot_id ? "" : `-${pair.persona}`}`}
      title={personaLabel(t, pair.persona)}
      badges={
        <>
          <SourceBadge source={pair.source} />
          {pair.optional && (
            <Badge variant="subtle">{t("route.optional")}</Badge>
          )}
        </>
      }
    >
      <span className="po-person-name">
        {name.trim() === "" ? t("route.noName") : name}
      </span>
      {when && <span className="po-note">{when}</span>}
      <span className="po-mono po-note">{`${names(pair.doc_id)} / ${pair.slot_id}`}</span>
    </PickItem>
  );
};

const SkippedCard = ({
  point,
  skip,
  names,
  outcome,
}: {
  point: OutcomePoint;
  skip: OutcomePoint["route"]["skipped"][number];
  names: Names;
  outcome: PackOutcome;
}) => {
  const { t } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const reasons = explain.reasons(skip.why);
  const when = whenText(t, skip.when);
  return (
    <PaleSlot
      el={{
        section: "route",
        id: skippedId(point.id, skip.doc_id, skip.slot_id),
      }}
      testId={`outcome-skipped-${point.id}-${skip.doc_id}-${skip.slot_id}`}
      name={`${names(skip.doc_id)}: ${personaLabel(t, skip.slot_id)}`}
    >
      {when && <span className="po-note">{when}</span>}
      <Reason
        prefix={t("route.skippedPrefix")}
        texts={reasons.length > 0 ? reasons : [t("route.skippedUnknown")]}
      />
    </PaleSlot>
  );
};

const MayAdd = ({
  point,
  names,
  forceOpen,
}: {
  point: OutcomePoint;
  names: Names;
  forceOpen: boolean;
}) => {
  const { t } = useTranslation("packOutcome");
  const bySlot = groupBy(point.route.may_add, (m) => m.slot_id);
  return (
    <Disclosure
      label={t("route.mayAddBlock")}
      count={point.route.may_add.length}
      forceOpen={forceOpen}
      testId={`outcome-route-${point.id}-mayadd`}
    >
      <p className="po-note">{t("route.mayAddLead")}</p>
      <ul className="po-mayadd">
        {bySlot.map(([slot, list]) => (
          <li key={slot} className="po-mayadd-row">
            <span className="po-mayadd-slot">{personaLabel(t, slot)}</span>
            <span className="po-mayadd-docs">
              {list.map((m) => (
                <Badge key={m.doc_id} variant="subtle">
                  {names(m.doc_id)}
                </Badge>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
};

const RouteCard = ({
  point,
  pairs,
  skipped,
  outcome,
  names,
  absent,
  forceOpen,
}: {
  point: OutcomePoint;
  pairs: Pair[];
  skipped: OutcomePoint["route"]["skipped"];
  outcome: PackOutcome;
  names: Names;
  absent: ReadonlySet<string>;
  forceOpen: boolean;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const route = point.route;
  const heading = useId();
  const who = new Map<string, string>();
  for (const step of route.steps) {
    for (const person of step) who.set(person.persona, person.name);
  }
  const groups = groupBy(pairs, (p) => p.doc_id);
  return (
    <li className="po-form po-route" data-testid={`outcome-route-${point.id}`}>
      <div className="po-route-head">
        <h4 className="po-route-title" id={heading}>
          {pickLocalized(point.name, i18n.language, point.id)}
        </h4>
        <span className="po-route-meta">
          <Badge
            variant="subtle"
            data-testid={`outcome-route-${point.id}-order`}
            data-source={route.order_source}
          >
            {`${t("route.order")} ${t(`route.orderSource.${route.order_source}`)}`}
          </Badge>
          {route.preset && <Badge variant="info">{t("route.preset")}</Badge>}
        </span>
      </div>
      <ol
        className="po-lane"
        aria-label={t("route.stepsLabel", {
          point: pickLocalized(point.name, i18n.language, point.id),
        })}
        data-testid={`outcome-route-${point.id}-steps`}
      >
        {route.steps.map((step, index) => (
          <Step
            key={String(index)}
            point={point}
            index={index}
            step={step}
            absent={absent}
          />
        ))}
      </ol>
      {groups.length > 0 && (
        <>
          <h5 className="po-sub-title">{t("route.pairs")}</h5>
          {groups.map(([doc, list]) => (
            <PairGroup
              key={doc}
              point={point}
              doc={doc}
              pairs={list}
              names={names}
              who={who}
            />
          ))}
        </>
      )}
      {skipped.length > 0 && (
        <Disclosure
          label={t("route.skippedBlock")}
          count={skipped.length}
          forceOpen={forceOpen}
          testId={`outcome-route-${point.id}-skipped`}
        >
          <ul className="po-grid">
            {skipped.map((skip) => (
              <SkippedCard
                key={`${skip.doc_id}/${skip.slot_id}`}
                point={point}
                skip={skip}
                names={names}
                outcome={outcome}
              />
            ))}
          </ul>
        </Disclosure>
      )}
      {route.may_add.length > 0 && (
        <MayAdd point={point} names={names} forceOpen={forceOpen} />
      )}
    </li>
  );
};

const PairGroup = ({
  point,
  doc,
  pairs,
  names,
  who,
}: {
  point: OutcomePoint;
  doc: string;
  pairs: Pair[];
  names: Names;
  who: ReadonlyMap<string, string>;
}) => {
  const id = useId();
  return (
    <div className="po-group po-pairs">
      <GroupTitle id={id} count={pairs.length}>
        {names(doc)}
      </GroupTitle>
      <ul className="po-grid" aria-labelledby={id}>
        {pairs.map((pair) => (
          <PairCard
            key={`${pair.slot_id}/${pair.persona}`}
            point={point}
            pair={pair}
            names={names}
            who={who}
          />
        ))}
      </ul>
    </div>
  );
};

const RouteBody = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const names = useDocNames(outcome);
  const lang = i18n.language;
  const [query, setQuery] = useState("");
  const [only, setOnly] = useState("");
  const selectId = useId();
  const points = outcome.points;
  const absent = absentPersonas(outcome);
  const empties = emptySteps(outcome, lang);

  const signed = (p: OutcomePoint) =>
    p.route.steps.length > 0 || p.route.pairs.length > 0;
  const stats = points.reduce(
    (n, p) => ({
      points: n.points + (signed(p) ? 1 : 0),
      steps: n.steps + p.route.steps.length,
      pairs: n.pairs + p.route.pairs.length,
      skipped: n.skipped + p.route.skipped.length,
      mayAdd: n.mayAdd + p.route.may_add.length,
    }),
    { points: 0, steps: 0, pairs: 0, skipped: 0, mayAdd: 0 },
  );

  const filtering = query.trim() !== "" || only !== "";
  const scoped = points.filter((p) => only === "" || p.id === only);
  const cards = scoped
    .filter(signed)
    .map((point) => {
      const whole = matches(
        query,
        pickLocalized(point.name, lang, point.id),
        point.id,
      );
      const who = new Map<string, string>();
      for (const step of point.route.steps) {
        for (const person of step) who.set(person.persona, person.name);
      }
      const pairs = point.route.pairs.filter(
        (p) =>
          whole ||
          matches(
            query,
            names(p.doc_id),
            p.doc_id,
            p.slot_id,
            p.persona,
            who.get(p.persona) ?? null,
          ),
      );
      const skipped = point.route.skipped.filter(
        (s) => whole || matches(query, names(s.doc_id), s.doc_id, s.slot_id),
      );
      const visible = whole || pairs.length > 0 || skipped.length > 0;
      return { point, pairs, skipped, visible };
    })
    .filter((x) => x.visible);
  const unsigned = scoped.filter(
    (p) =>
      !signed(p) && matches(query, pickLocalized(p.name, lang, p.id), p.id),
  );
  const reset = () => {
    setQuery("");
    setOnly("");
  };

  return (
    <div
      className="po-sec"
      data-stale={stale ? "true" : undefined}
      data-testid="outcome-route"
      onKeyDown={onArrowNav}
    >
      <StepWarning steps={empties} testId="outcome-route-warning" />
      <Stats
        testId="outcome-route-stats"
        items={[
          { id: "points", label: t("route.stats.points"), value: stats.points },
          { id: "steps", label: t("route.stats.steps"), value: stats.steps },
          { id: "pairs", label: t("route.stats.pairs"), value: stats.pairs },
          {
            id: "skipped",
            label: t("route.stats.skipped"),
            value: stats.skipped,
          },
          { id: "mayAdd", label: t("route.stats.mayAdd"), value: stats.mayAdd },
        ]}
      />
      {points.length === 0 ? (
        <p className="po-note" data-testid="outcome-route-empty">
          {t("route.empty")}
        </p>
      ) : (
        <>
          <FilterBar
            label={t("sections.route")}
            query={query}
            onQuery={setQuery}
            testId="outcome-route-filter"
          >
            <label className="po-filter-select" htmlFor={selectId}>
              <span className="po-note">{t("route.filterPoint")}</span>
              <select
                id={selectId}
                className="input"
                value={only}
                data-testid="outcome-route-only"
                onChange={(e) => {
                  setOnly(e.target.value);
                }}
              >
                <option value="">{t("route.filterAll")}</option>
                {points.map((p) => (
                  <option key={p.id} value={p.id}>
                    {pickLocalized(p.name, lang, p.id)}
                  </option>
                ))}
              </select>
            </label>
          </FilterBar>
          {filtering && cards.length === 0 && unsigned.length === 0 ? (
            <NoResults
              compact
              query={query}
              onReset={reset}
              testId="outcome-route-noresults"
            />
          ) : (
            <>
              {cards.length > 0 && (
                <ul className="po-forms" data-testid="outcome-route-list">
                  {cards.map(({ point, pairs, skipped }) => (
                    <RouteCard
                      key={point.id}
                      point={point}
                      pairs={pairs}
                      skipped={skipped}
                      outcome={outcome}
                      names={names}
                      absent={absent}
                      forceOpen={query.trim() !== ""}
                    />
                  ))}
                </ul>
              )}
              {unsigned.length > 0 && (
                <Disclosure
                  label={t("route.noRouteBlock")}
                  count={unsigned.length}
                  forceOpen={filtering}
                  testId="outcome-route-unsigned"
                >
                  <p className="po-note">{t("route.noRouteLead")}</p>
                  <ul className="po-unsigned">
                    {unsigned.map((p) => (
                      <li key={p.id} data-testid={`outcome-route-${p.id}-none`}>
                        <span>{pickLocalized(p.name, lang, p.id)}</span>
                        <span className="po-note">
                          {`${t("route.order")} ${t(`route.orderSource.${p.route.order_source}`)}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Disclosure>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};

/** Маршрут подписания по точкам: шаги порядком, пары слот и персона, пропущенные, `may_add`. */
export const RouteSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="route"
      title={t("sections.route")}
      count={sum ? t("sections.count.route", { count: sum.routes }) : null}
      loading={!shown}
    >
      {shown && <RouteBody outcome={shown} />}
    </SectionShell>
  );
};
