import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PackOutcome, ScenarioAssertion } from "@entities/pack-studio";
import {
  ASSERTION_KINDS,
  assertionKey,
  describeAssertion,
  namesOf,
  suggestAssertions,
  type AssertionKind,
} from "../../lib/scenarios";

type AssertionsEditorProps = {
  value: ScenarioAssertion[];
  onChange: (next: ScenarioAssertion[]) => void;
  /** Результат, из которого берутся готовые утверждения; нет результата: только уже записанные. */
  outcome: PackOutcome | undefined;
  disabled?: boolean | undefined;
};

/**
 * Утверждения сценария: уже записанные и готовые по текущему результату («есть документ X»,
 * «нет документа X», «подписант Y в маршруте», «пункт Z активен»). Виды закрыты на сервере, поэтому
 * текст утверждения вручную не пишется: утверждают то, что результат показывает сейчас.
 */
export const AssertionsEditor = ({
  value,
  onChange,
  outcome,
  disabled,
}: AssertionsEditorProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  // Уже записанные остаются в списке, даже если результат их больше не предлагает.
  const [initial] = useState(value);
  const rows = useMemo(() => {
    const seen = new Set<string>();
    const out: ScenarioAssertion[] = [];
    for (const item of [
      ...initial,
      ...(outcome ? suggestAssertions(outcome) : []),
    ]) {
      const key = assertionKey(item);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  }, [initial, outcome]);
  const names = useMemo(
    () => namesOf(outcome, i18n.language, t),
    [outcome, i18n.language, t],
  );
  const selected = useMemo(() => new Set(value.map(assertionKey)), [value]);

  const set = (keys: ReadonlySet<string>) => {
    onChange(rows.filter((row) => keys.has(assertionKey(row))));
  };
  const toggle = (row: ScenarioAssertion, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(assertionKey(row));
    else next.delete(assertionKey(row));
    set(next);
  };
  const groups = ASSERTION_KINDS.map((kind) => ({
    kind,
    rows: rows.filter((row) => row.kind === kind),
  })).filter((group) => group.rows.length > 0);

  return (
    <div className="po-sc-assertions" data-testid="scenario-assertions">
      <div className="po-sc-assertions-bar">
        <span className="po-sc-count" role="status">
          {t("scenarios.assertions.selected", {
            count: value.length,
          })}
        </span>
        <button
          type="button"
          className="po-link"
          disabled={disabled === true || rows.length === 0}
          data-testid="scenario-assert-all"
          onClick={() => {
            set(new Set(rows.map(assertionKey)));
          }}
        >
          {t("scenarios.assertions.all")}
        </button>
        <button
          type="button"
          className="po-link"
          disabled={disabled === true || value.length === 0}
          data-testid="scenario-assert-none"
          onClick={() => {
            set(new Set());
          }}
        >
          {t("scenarios.assertions.none")}
        </button>
      </div>
      {outcome === undefined && (
        <p className="po-in-hint">{t("scenarios.assertions.noResult")}</p>
      )}
      {groups.map(({ kind, rows: list }) => (
        <Group
          key={kind}
          kind={kind}
          open={list.some((row) => selected.has(assertionKey(row)))}
          selectedCount={
            list.filter((row) => selected.has(assertionKey(row))).length
          }
          total={list.length}
        >
          {list.map((row) => {
            const key = assertionKey(row);
            return (
              <label key={key} className="po-check">
                <input
                  type="checkbox"
                  checked={selected.has(key)}
                  disabled={disabled}
                  onChange={(event) => {
                    toggle(row, event.target.checked);
                  }}
                />
                <span>{describeAssertion(row, names, t)}</span>
              </label>
            );
          })}
        </Group>
      ))}
    </div>
  );
};

type GroupProps = {
  kind: AssertionKind;
  open: boolean;
  selectedCount: number;
  total: number;
  children: React.ReactNode;
};

const Group = ({ kind, open, selectedCount, total, children }: GroupProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <details
      className="po-sc-group"
      open={open}
      data-testid={`scenario-group-${kind}`}
    >
      <summary>
        {t(`scenarios.kind.${kind}`)}
        <span className="po-inputs-count">
          {t("scenarios.assertions.groupCount", {
            selected: selectedCount,
            total,
          })}
        </span>
      </summary>
      <div className="po-sc-group-body">{children}</div>
    </details>
  );
};
