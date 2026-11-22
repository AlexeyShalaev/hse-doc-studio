import type { TFunction } from "i18next";
import type { OutcomeChange } from "@entities/pack-studio";
import type { Naming } from "./naming";

// Изменения «Сравнить» человеческими словами (pack-studio-ux.md, раздел 5.7 и 6): сервер называет
// части результата по виду и идентификатору («участник supervisor», «topic-approval: шаг 2») и
// пишет «было» и «стало» значениями версии («supervisor, co_supervisor»). Здесь подпись и значения
// строятся заново из вида изменения и названий пака; сырой вид записывается в «Технические
// подробности». Чего разобрать не удалось, не показывается вовсе.

export type PlainChange = {
  label: string;
  before: string | null;
  after: string | null;
  tech: { label: string; value: string }[];
};

const split = (id: string): [string, string, string] => {
  const [a = "", b = "", ...rest] = id.split("/");
  return [a, b, rest.join("/")];
};

const list = (text: string): string[] =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");

const labelOf = (
  change: OutcomeChange,
  naming: Naming,
  t: TFunction,
): string => {
  const [head, second, third] = split(change.id);
  switch (change.kind) {
    case "document":
      return t("plain.change.label.document", {
        name: naming.document(change.id),
      });
    case "variant":
      return t("plain.change.label.variant", { name: naming.document(head) });
    case "meta_field":
      return t("plain.change.label.metaField", {
        name: naming.element("meta", change.id),
      });
    case "form":
      return t("plain.change.label.form");
    case "form_field":
      return t("plain.change.label.formField");
    case "participant":
      return t("plain.change.label.participant", {
        name: naming.role(change.id),
      });
    case "point":
      return t("plain.change.label.point", { name: naming.point(change.id) });
    case "item":
      return t("plain.change.label.item", {
        point: naming.point(head),
        document: naming.document(second),
      });
    case "extra_item":
      return t("plain.change.label.extra", { point: naming.point(head) });
    case "route_step": {
      const step = /step\/(\d+)/.exec(change.id)?.[1] ?? "";
      return t("plain.change.label.step", {
        point: naming.point(head),
        n: step,
      });
    }
    case "route_pair":
    case "skipped_pair":
      return t(
        change.kind === "skipped_pair"
          ? "plain.change.label.skipped"
          : "plain.change.label.pair",
        {
          point: naming.point(head),
          document: naming.document(second),
          signature: naming.slot(third.split("/")[0] ?? ""),
        },
      );
    case "may_add":
      return t("plain.change.label.mayAdd", { point: naming.point(head) });
    case "check_rule":
      return t("plain.change.label.check");
  }
};

const yesNo = (value: string, t: TFunction): string =>
  value === "true" ? t("plain.change.yes") : t("plain.change.no");

const reasonOf = (reason: string, t: TFunction): string =>
  t(`plain.change.reason.${reason}`, { defaultValue: "" });

/** Значение одной стороны: вид и строка сервера в слова; `null`, если строку не разобрать. */
const valueOf = (
  kind: OutcomeChange["kind"],
  raw: string,
  naming: Naming,
  t: TFunction,
): string | null => {
  const roles = (text: string): string =>
    list(text)
      .map((id) => naming.role(id))
      .join(", ");
  switch (kind) {
    case "document": {
      const match = /^(\w+)(?:\s+\[(.*)\])?$/.exec(raw);
      if (!match?.[1]) return null;
      const state = t(`plain.change.docState.${match[1]}`, {
        defaultValue: "",
      });
      if (state === "") return null;
      return match[2]
        ? t("plain.change.docOwners", { state, who: roles(match[2]) })
        : state;
    }
    case "meta_field": {
      const match = /^(visible|hidden), required_at=(\w+)$/.exec(raw);
      if (!match?.[1] || !match[2]) return null;
      return t("plain.change.metaValue", {
        shown: t(`plain.change.${match[1]}`),
        required: t(`plain.change.requiredAt.${match[2]}`, {
          defaultValue: "",
        }),
      });
    }
    case "form": {
      const match = /^applies=(\w+), per_author=(\w+)$/.exec(raw);
      if (!match?.[1] || !match[2]) return null;
      return t("plain.change.formValue", {
        applies: yesNo(match[1], t),
        perAuthor: yesNo(match[2], t),
      });
    }
    case "form_field": {
      const match = /^(visible|hidden), required=(\w+)$/.exec(raw);
      if (!match?.[1] || !match[2]) return null;
      return t("plain.change.fieldValue", {
        shown: t(`plain.change.${match[1]}`),
        required: yesNo(match[2], t),
      });
    }
    case "item":
    case "extra_item": {
      const match = /^(active|off)(?:\s+\(([^)]*)\))?(?:\s+\[(.*)\])?$/.exec(
        raw,
      );
      if (!match?.[1]) return null;
      const reason = match[2] ? reasonOf(match[2], t) : "";
      const base = t(`plain.change.item.${match[1]}`);
      const signers = match[3]
        ? list(match[3])
            .map((id) => naming.slot(id))
            .join(", ")
        : "";
      return [
        base,
        reason,
        signers === "" ? "" : t("plain.change.signedBy", { who: signers }),
      ]
        .filter((part) => part !== "")
        .join(", ");
    }
    case "route_step":
      return roles(raw);
    case "route_pair": {
      const match = /^(\S+)\s+\((\w+)(, optional)?\)$/.exec(raw);
      if (!match?.[1]) return null;
      return [naming.role(match[1]), match[3] ? t("plain.change.optional") : ""]
        .filter((part) => part !== "")
        .join(", ");
    }
    case "may_add": {
      const slots = list(raw).map((pair) =>
        naming.slot(pair.split("/")[1] ?? ""),
      );
      return slots.join(", ");
    }
    case "check_rule": {
      const match = /^(enabled|off)(?:\s+\(([^)]*)\))?/.exec(raw);
      if (!match?.[1]) return null;
      return t(`plain.change.check.${match[1]}`);
    }
    default:
      return null;
  }
};

export const plainChange = (
  change: OutcomeChange,
  naming: Naming,
  t: TFunction,
): PlainChange => {
  const side = (raw: string | null): string | null =>
    raw === null ? null : valueOf(change.kind, raw, naming, t);
  const tech: PlainChange["tech"] = [
    { label: t("plain.tech.kind"), value: change.kind },
    { label: t("plain.tech.id"), value: change.id },
    { label: t("plain.tech.message"), value: change.label },
  ];
  if (change.before !== null) {
    tech.push({ label: t("plain.tech.before"), value: change.before });
  }
  if (change.after !== null) {
    tech.push({ label: t("plain.tech.after"), value: change.after });
  }
  return {
    label: labelOf(change, naming, t),
    before: side(change.before),
    after: side(change.after),
    tech,
  };
};
