import type { TFunction } from "i18next";
import type { PackOutcome, ScenarioAssertion } from "@entities/pack-studio";
import type { AssertionKind } from "@entities/pack-studio/outcome/scenarios";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import type { Naming } from "../../plain/naming";

// «Что должно получаться» у готового случая словами (pack-studio-ux.md, 5.7 и раздел 6): сервер
// хранит закрытый набор утверждений (документ есть, участник есть, пункт нужен ...). Здесь они
// описываются русским текстом по названиям пака и результата; идентификатор наружу не выходит.

export type ExpectNames = {
  doc: (id: string) => string;
  field: (id: string) => string;
  point: (id: string) => string;
  role: (id: string) => string;
  signature: (id: string) => string;
};

/** Названия из результата случая (документы, поля, точки сдачи) и из пака (роли, подписи). */
export const expectNamesOf = (
  outcome: PackOutcome | undefined,
  lng: string,
  naming: Naming,
  t: TFunction,
): ExpectNames => {
  const docs = new Map(
    (outcome?.documents ?? []).map((item) => [item.id, item.name]),
  );
  const fields = new Map(
    (outcome?.meta ?? []).map((item) => [item.id, item.label]),
  );
  const points = new Map(
    (outcome?.points ?? []).map((item) => [item.id, item.name]),
  );
  const named = (
    map: ReadonlyMap<string, Record<string, string> | null>,
    id: string,
    fallback: string,
  ): string => {
    const found = map.get(id);
    return found ? pickLocalized(found, lng, fallback) : fallback;
  };
  return {
    doc: (id) => named(docs, id, naming.document(id)),
    field: (id) => named(fields, id, t("plain.fallback.metaField")),
    point: (id) => named(points, id, naming.point(id)),
    role: (id) => naming.role(id),
    signature: (id) => naming.slot(id),
  };
};

/** Утверждение одной фразой. */
export const describeExpect = (
  item: ScenarioAssertion,
  names: ExpectNames,
  t: TFunction,
): string => {
  switch (item.kind) {
    case "document_state":
      return t(`check.expect.say.document_state.${item.state}`, {
        doc: names.doc(item.doc),
      });
    case "document_count":
      return t(`check.expect.say.document_count.${item.state}`, {
        count: item.count,
      });
    case "meta_visible":
      return t(
        item.visible
          ? "check.expect.say.meta_visible.yes"
          : "check.expect.say.meta_visible.no",
        { field: names.field(item.field) },
      );
    case "participant_present":
      return t(
        item.present
          ? "check.expect.say.participant_present.yes"
          : "check.expect.say.participant_present.no",
        { role: names.role(item.persona) },
      );
    case "item_active":
      return t(
        item.active
          ? "check.expect.say.item_active.yes"
          : "check.expect.say.item_active.no",
        { doc: names.doc(item.doc), point: names.point(item.point) },
      );
    case "route_steps":
      return t("check.expect.say.route_steps", {
        point: names.point(item.point),
        steps:
          item.steps.length === 0
            ? t("check.expect.say.noSteps")
            : item.steps
                .map(
                  (step, index) =>
                    `${String(index + 1)}. ${step.map((id) => names.role(id)).join(" + ")}`,
                )
                .join("; "),
      });
    case "route_pair":
      return t(
        item.present
          ? "check.expect.say.route_pair.yes"
          : "check.expect.say.route_pair.no",
        {
          role: names.role(item.persona),
          signature: names.signature(item.slot),
          doc: names.doc(item.doc),
          point: names.point(item.point),
        },
      );
  }
};

/** Заголовок группы готовых ожиданий в списке «Добавить». */
export const expectKindLabel = (kind: AssertionKind, t: TFunction): string =>
  t(`check.expect.kind.${kind}`);
