import { useId, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomePoint, PackOutcome } from "@entities/pack-studio";
import { Badge, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { extraId, itemId, pointId } from "../../lib/routeIds";
import { personaLabel } from "../../lib/personas";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import "../../outcomeRoute.css";
import { AddInputAction } from "./PaleSlot";
import { SectionShell } from "./SectionShell";
import { Disclosure, FilterBar, PickButton, Reason, Stats } from "./parts";
import { matches, onArrowNav, useIsSelected } from "./helpers";
import { useDocNames } from "./useDocNames";
import { useExplain } from "./useExplain";

type Names = (id: string) => string;
type PointItem = OutcomePoint["items"][number];
type PointExtra = OutcomePoint["extra_items"][number];

/** Кнопка «К документу»: выбирает документ, и он подсвечивается в секции «Документы». */
const DocLink = ({
  point,
  doc,
  name,
}: {
  point: string;
  doc: string;
  name: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const { reveal } = useOutcomeModel();
  const selected = useIsSelected({ section: "documents", id: doc });
  return (
    <button
      type="button"
      className="po-link-btn"
      data-po-pick="true"
      aria-label={t("points.openDocLabel", { name })}
      aria-pressed={selected}
      data-testid={`outcome-doc-link-${point}-${doc}`}
      onClick={() => {
        // Повторный клик не снимает выбор: ссылка ведёт к документу, а не переключает его;
        // на телефоне она открывает вкладку «Почему?» и тогда, когда документ уже выбран.
        reveal({ section: "documents", id: doc });
      }}
    >
      <ArrowUpRight size="0.8125rem" aria-hidden="true" />
      <span>{t("points.openDoc")}</span>
    </button>
  );
};

const OffBadge = ({ reason }: { reason: PointItem["off_reason"] }) => {
  const { t } = useTranslation("packOutcome");
  return (
    <Badge variant="warning">
      {reason ? t(`points.off.${reason}`) : t("points.whyUnknown")}
    </Badge>
  );
};

const ItemRow = ({
  point,
  item,
  names,
  outcome,
}: {
  point: OutcomePoint;
  item: PointItem;
  names: Names;
  outcome: PackOutcome;
}) => {
  const { t } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const id = itemId(point.id, item.doc_id);
  const selected = useIsSelected({ section: "points", id });
  const name = names(item.doc_id);
  const reasons = item.active ? [] : explain.reasons(item.why);
  return (
    <li
      className="po-item po-row"
      data-muted={item.active ? undefined : "true"}
      data-pale={item.active ? undefined : "true"}
      data-selected={selected ? "true" : undefined}
      data-testid={`outcome-item-${point.id}-${item.doc_id}`}
    >
      <PickButton
        el={{ section: "points", id }}
        title={name}
        badges={item.active ? undefined : <OffBadge reason={item.off_reason} />}
      >
        {item.active ? (
          <span className="po-note">
            {item.signatures.length > 0
              ? `${t("points.signatures")} ${item.signatures
                  .map((s) => personaLabel(t, s))
                  .join(", ")}`
              : t("points.noSignatures")}
          </span>
        ) : (
          <Reason
            prefix={t("points.offPrefix")}
            texts={reasons.length > 0 ? reasons : [t("points.whyUnknown")]}
          />
        )}
      </PickButton>
      {item.active ? (
        <DocLink point={point.id} doc={item.doc_id} name={name} />
      ) : (
        <AddInputAction el={{ section: "points", id }} name={name} />
      )}
    </li>
  );
};

const ExtraRow = ({
  point,
  extra,
  outcome,
}: {
  point: OutcomePoint;
  extra: PointExtra;
  outcome: PackOutcome;
}) => {
  const { t } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const id = extraId(point.id, extra.source);
  const selected = useIsSelected({ section: "points", id });
  const reasons = extra.active ? [] : explain.reasons(extra.why);
  return (
    <li
      className="po-item po-row"
      data-muted={extra.active ? undefined : "true"}
      data-pale={extra.active ? undefined : "true"}
      data-selected={selected ? "true" : undefined}
      data-testid={`outcome-extra-${point.id}-${extra.output_name}`}
    >
      <PickButton
        el={{ section: "points", id }}
        title={extra.output_name}
        badges={
          <>
            {extra.format && <Badge variant="subtle">{extra.format}</Badge>}
            {!extra.active && <OffBadge reason={extra.off_reason} />}
          </>
        }
      >
        <span className="po-note">
          {t("points.extraFrom", { source: extra.source })}
        </span>
        {!extra.active && (
          <Reason
            prefix={t("points.offPrefix")}
            texts={reasons.length > 0 ? reasons : [t("points.whyUnknown")]}
          />
        )}
      </PickButton>
      {!extra.active && (
        <AddInputAction
          el={{ section: "points", id }}
          name={extra.output_name}
        />
      )}
    </li>
  );
};

const PointCard = ({
  point,
  items,
  extras,
  outcome,
  names,
  forceOpen,
}: {
  point: OutcomePoint;
  items: PointItem[];
  extras: PointExtra[];
  outcome: PackOutcome;
  names: Names;
  forceOpen: boolean;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const lang = i18n.language;
  const el = { section: "points", id: pointId(point.id) } as const;
  const selected = useIsSelected(el);
  const headId = useId();
  const on = items.filter((i) => i.active);
  const off = items.filter((i) => !i.active);
  const hint = point.deadline_hint
    ? pickLocalized(point.deadline_hint, lang, "")
    : "";
  const signed = point.route.pairs.length;
  return (
    <li
      className="po-form po-point"
      data-selected={selected ? "true" : undefined}
      data-testid={`outcome-point-${point.id}`}
    >
      <PickButton
        el={el}
        testId={`outcome-point-${point.id}-pick`}
        title={pickLocalized(point.name, lang, point.id)}
        badges={
          <>
            <Badge variant="accent">
              {t("points.itemsOf", {
                count: point.items.length,
                active: point.items.filter((i) => i.active).length,
                total: point.items.length,
              })}
            </Badge>
            {signed > 0 && (
              <Badge>{t("points.signed", { count: signed })}</Badge>
            )}
          </>
        }
      >
        {hint !== "" && (
          <span
            className="po-note"
            data-testid={`outcome-point-${point.id}-hint`}
          >
            <span className="po-point-hint">{t("points.deadline")}</span> {hint}
          </span>
        )}
        <span className="po-mono po-note">{point.id}</span>
      </PickButton>
      {point.items.length === 0 && point.extra_items.length === 0 ? (
        <p className="po-note po-point-empty">{t("points.noItems")}</p>
      ) : (
        <>
          {on.length > 0 && (
            <>
              <h5 className="po-sub-title" id={headId}>
                {t("points.items")}
              </h5>
              <ul className="po-rows" aria-labelledby={headId}>
                {on.map((item) => (
                  <ItemRow
                    key={item.doc_id}
                    point={point}
                    item={item}
                    names={names}
                    outcome={outcome}
                  />
                ))}
              </ul>
            </>
          )}
          {extras.length > 0 && (
            <>
              <h5 className="po-sub-title">{t("points.extra")}</h5>
              <ul
                className="po-rows"
                data-testid={`outcome-point-${point.id}-extra`}
              >
                {extras.map((extra) => (
                  <ExtraRow
                    key={extra.source}
                    point={point}
                    extra={extra}
                    outcome={outcome}
                  />
                ))}
              </ul>
            </>
          )}
          {off.length > 0 && (
            <Disclosure
              label={t("points.offBlock")}
              count={off.length}
              forceOpen={forceOpen}
              testId={`outcome-point-${point.id}-off`}
            >
              <ul className="po-rows">
                {off.map((item) => (
                  <ItemRow
                    key={item.doc_id}
                    point={point}
                    item={item}
                    names={names}
                    outcome={outcome}
                  />
                ))}
              </ul>
            </Disclosure>
          )}
        </>
      )}
    </li>
  );
};

const PointsBody = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const names = useDocNames(outcome);
  const lang = i18n.language;
  const [query, setQuery] = useState("");
  const [only, setOnly] = useState("");
  const selectId = useId();
  const points = outcome.points;

  const stats = {
    active: points.reduce(
      (n, p) => n + p.items.filter((i) => i.active).length,
      0,
    ),
    off: points.reduce(
      (n, p) =>
        n +
        p.items.filter((i) => !i.active).length +
        p.extra_items.filter((e) => !e.active).length,
      0,
    ),
    extra: points.reduce(
      (n, p) => n + p.extra_items.filter((e) => e.active).length,
      0,
    ),
  };

  const filtering = query.trim() !== "" || only !== "";
  const shown = points
    .filter((p) => only === "" || p.id === only)
    .map((point) => {
      const whole = matches(
        query,
        pickLocalized(point.name, lang, point.id),
        point.id,
      );
      const items = point.items.filter(
        (i) => whole || matches(query, names(i.doc_id), i.doc_id),
      );
      const extras = point.extra_items.filter(
        (e) => whole || matches(query, e.output_name, e.source),
      );
      const visible = whole || items.length > 0 || extras.length > 0;
      return { point, items, extras, visible };
    })
    .filter((x) => x.visible);
  const reset = () => {
    setQuery("");
    setOnly("");
  };

  return (
    <div
      className="po-sec"
      data-stale={stale ? "true" : undefined}
      data-testid="outcome-points"
      onKeyDown={onArrowNav}
    >
      <Stats
        testId="outcome-points-stats"
        items={[
          {
            id: "points",
            label: t("points.stats.points"),
            value: points.length,
          },
          {
            id: "active",
            label: t("points.stats.active"),
            value: stats.active,
          },
          { id: "off", label: t("points.stats.off"), value: stats.off },
          { id: "extra", label: t("points.stats.extra"), value: stats.extra },
        ]}
      />
      {points.length === 0 ? (
        <p className="po-note" data-testid="outcome-points-empty">
          {t("points.empty")}
        </p>
      ) : (
        <>
          <FilterBar
            label={t("sections.points")}
            query={query}
            onQuery={setQuery}
            testId="outcome-points-filter"
          >
            <label className="po-filter-select" htmlFor={selectId}>
              <span className="po-note">{t("points.filterPoint")}</span>
              <select
                id={selectId}
                className="input"
                value={only}
                data-testid="outcome-points-only"
                onChange={(e) => {
                  setOnly(e.target.value);
                }}
              >
                <option value="">{t("points.filterAll")}</option>
                {points.map((p) => (
                  <option key={p.id} value={p.id}>
                    {pickLocalized(p.name, lang, p.id)}
                  </option>
                ))}
              </select>
            </label>
          </FilterBar>
          {filtering && shown.length === 0 ? (
            <NoResults
              compact
              query={query}
              onReset={reset}
              testId="outcome-points-noresults"
            />
          ) : (
            <ul className="po-forms" data-testid="outcome-points-list">
              {shown.map(({ point, items, extras }) => (
                <PointCard
                  key={point.id}
                  point={point}
                  items={items}
                  extras={extras}
                  outcome={outcome}
                  names={names}
                  forceOpen={query.trim() !== ""}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
};

/** Точки сдачи: что и когда сдаётся, какие пункты выключены и почему. */
export const PointsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="points"
      title={t("sections.points")}
      count={sum ? t("sections.count.points", { count: sum.points }) : null}
      loading={!shown}
    >
      {shown && <PointsBody outcome={shown} />}
    </SectionShell>
  );
};
