import { useId, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackOutcome, ScenarioAssertion } from "@entities/pack-studio";
import {
  ASSERTION_KINDS,
  assertionKey,
  suggestAssertions,
} from "@entities/pack-studio/outcome/scenarios";
import { describeExpect, expectKindLabel, type ExpectNames } from "./expect";

/**
 * «Что должно получаться»: ожидания готового случая словами. Видно, что уже ожидается (у каждого
 * «Убрать»), и можно добавить любое из того, что результат показывает сейчас («Добавить»,
 * «Добавить всё, что есть сейчас»). Виды ожиданий закрыты на сервере, поэтому текст не пишется
 * руками: ожидают то, что случай даёт на самом деле.
 */
export const ExpectEditor = ({
  value,
  onChange,
  outcome,
  names,
  disabled = false,
}: {
  value: ScenarioAssertion[];
  onChange: (next: ScenarioAssertion[]) => void;
  /** Результат случая; без него предложить нечего. */
  outcome: PackOutcome | undefined;
  names: ExpectNames;
  disabled?: boolean;
}) => {
  const { t } = useTranslation("packSpace");
  const [pick, setPick] = useState("");
  const selectId = useId();
  const chosen = useMemo(() => new Set(value.map(assertionKey)), [value]);
  const offers = useMemo(
    () =>
      (outcome ? suggestAssertions(outcome) : []).filter(
        (item) => !chosen.has(assertionKey(item)),
      ),
    [outcome, chosen],
  );
  const groups = ASSERTION_KINDS.map((kind) => ({
    kind,
    items: offers.filter((item) => item.kind === kind),
  })).filter((group) => group.items.length > 0);

  const add = (items: readonly ScenarioAssertion[]) => {
    onChange([...value, ...items]);
    setPick("");
  };
  const picked = offers.find((item) => assertionKey(item) === pick);

  return (
    <div className="sp-ck-expect" data-testid="case-expect">
      {value.length === 0 ? (
        <p className="sp-ck-note" data-testid="case-expect-empty">
          {t("check.expect.none")}
        </p>
      ) : (
        <ul className="sp-ck-expect-list" aria-label={t("check.expect.list")}>
          {value.map((item) => {
            const text = describeExpect(item, names, t);
            return (
              <li key={assertionKey(item)} data-testid="case-expect-item">
                <span>{text}</span>
                {!disabled && (
                  <button
                    type="button"
                    className="btn sm"
                    aria-label={t("check.expect.removeOne", { text })}
                    onClick={() => {
                      onChange(
                        value.filter(
                          (other) => assertionKey(other) !== assertionKey(item),
                        ),
                      );
                    }}
                  >
                    <X size="0.75rem" aria-hidden="true" />
                    {t("check.expect.remove")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {!disabled && (
        <div className="sp-ck-expect-add">
          {offers.length === 0 ? (
            <p className="sp-ck-note">
              {outcome === undefined
                ? t("check.expect.noResult")
                : t("check.expect.allAdded")}
            </p>
          ) : (
            <>
              <label className="sp-ck-field" htmlFor={selectId}>
                <span className="sp-ck-note">{t("check.expect.addLabel")}</span>
                <select
                  id={selectId}
                  className="input"
                  value={pick}
                  onChange={(event) => {
                    setPick(event.target.value);
                  }}
                >
                  <option value="">{t("check.expect.addPlaceholder")}</option>
                  {groups.map((group) => (
                    <optgroup
                      key={group.kind}
                      label={expectKindLabel(group.kind, t)}
                    >
                      {group.items.map((item) => (
                        <option
                          key={assertionKey(item)}
                          value={assertionKey(item)}
                        >
                          {describeExpect(item, names, t)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <div className="sp-ck-actions">
                <button
                  type="button"
                  className="btn sm"
                  disabled={picked === undefined}
                  onClick={() => {
                    if (picked) add([picked]);
                  }}
                >
                  <Plus size="0.8125rem" aria-hidden="true" />
                  {t("check.expect.add")}
                </button>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => {
                    add(offers);
                  }}
                >
                  {t("check.expect.addAll", { count: offers.length })}
                </button>
              </div>
            </>
          )}
          {value.length > 0 && (
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                onChange([]);
              }}
            >
              {t("check.expect.removeAll")}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
