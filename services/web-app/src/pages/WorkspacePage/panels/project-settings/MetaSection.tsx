import { Files, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { i18n, isMetaValueBlank, pickLocalized } from "@shared/lib";
import { SectionCard } from "../SectionCard";
import {
  groupMetaFields,
  shouldShowMetaGroupHeadings,
  SHARED_META_BLOCK_KEY,
  type MetaBlock,
  type MetaFieldEntry,
  type MetaGroupDef,
} from "./sectionData";

export type MetaSectionProps = {
  fields: readonly MetaFieldEntry[];
  metaGroups: readonly MetaGroupDef[];
  // Заголовок карточки; по умолчанию — «Метаданные». Группа, уведённая паком
  // на другую страницу настроек, приходит сюда отдельной карточкой со своим
  // именем (см. buildMetaGroupCards).
  title?: string;
  // Подсказка над переключателем блоков (team); по умолчанию — про метаданные.
  teamHint?: string;
  // Подзаголовки групп внутри карточки. Карточка одной группы своё имя уже
  // несёт в заголовке — печатать его второй раз незачем.
  showGroupHeadings?: boolean;
  // Блоки раскладки: «Общие документы» + комплект каждого ведомого автора.
  blocks: readonly MetaBlock[];
  activeBlock: string;
  // Solo (и team с единственным блоком) переключателя не показывает.
  showBlockSwitcher: boolean;
  onSelectBlock: (key: string) => void;
  // Системные значения (project.meta): значения общего блока и одновременно
  // значения по умолчанию для авторов.
  sharedMeta: Record<string, unknown> | undefined;
  // Значения активного авторского блока; null — активен общий блок.
  authorMeta: Record<string, unknown> | null;
  onSetValue: (key: string, value: string, immediate: boolean) => void;
};

export const MetaSection = ({
  fields,
  metaGroups,
  title,
  teamHint,
  showGroupHeadings: showGroupHeadingsProp,
  blocks,
  activeBlock,
  showBlockSwitcher,
  onSelectBlock,
  sharedMeta,
  authorMeta,
  onSetValue,
}: MetaSectionProps) => {
  const { t } = useTranslation("workspace");
  const groups = groupMetaFields(
    [...fields],
    metaGroups,
    t("projectSettings.metaGroupOther"),
  );
  const showGroupHeadings =
    showGroupHeadingsProp ?? shouldShowMetaGroupHeadings(groups);

  return (
    <SectionCard title={title ?? t("projectSettings.sectionMeta")} fullSpan>
      {showBlockSwitcher && (
        <div className="flex flex-col" style={{ gap: 8, marginBottom: 14 }}>
          <span className="dim" style={{ fontSize: 11.5 }}>
            {teamHint ?? t("projectSettings.metaTeamHint")}
          </span>
          <div className="seg self-start">
            {blocks.map((b) => (
              <button
                key={b.key}
                type="button"
                className={clsx(activeBlock === b.key && "active")}
                onClick={() => {
                  onSelectBlock(b.key);
                }}
              >
                {b.key === SHARED_META_BLOCK_KEY ? (
                  <Files size={10} />
                ) : (
                  <Users size={10} />
                )}
                {b.label}
              </button>
            ))}
          </div>
        </div>
      )}
      {groups.map((grp, grpIdx) => (
        <div key={grp.id}>
          {showGroupHeadings && (
            <div
              className="dim"
              style={{
                fontSize: 10.5,
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                marginTop: grpIdx === 0 ? 0 : 16,
                marginBottom: 8,
              }}
            >
              {grp.label}
            </div>
          )}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: 12,
            }}
          >
            {grp.fields.map(([key, def]) => {
              const label = pickLocalized(def.label, i18n.language, key);
              const options = def.options ?? [];
              const sharedValue =
                (sharedMeta?.[key] as string | undefined) ?? "";
              const value = authorMeta
                ? ((authorMeta[key] as string | undefined) ?? "")
                : sharedValue;
              // `required_at` defaults to "create" when the pack omits it.
              const requiredAt = def.required_at ?? "create";
              const blank = isMetaValueBlank(value);
              // Пункт «своего значения нет» в авторском блоке: показываем само
              // унаследованное значение со стрелкой. Полная фраза «наследуется
              // от общих (Программиста и оператора)» в ширину селекта не
              // влезала и обрезалась на середине слова; что значение
              // унаследовано, договаривает подсказка под полем.
              const inheritedLabel = sharedValue
                ? `↳ ${sharedValue}`
                : t("projectSettings.metaInheritedEmpty");
              const setValue = (v: string, immediate: boolean) => {
                onSetValue(key, v, immediate);
              };
              return (
                <div key={key} className="field">
                  <label className="flex items-center gap-2">
                    <span>{label}</span>
                    {/* Обязательность относится к системным значениям —
                        авторские перекрытия всегда опциональны. */}
                    {!authorMeta && requiredAt === "create" && (
                      <span style={{ color: "var(--c-err)" }}>*</span>
                    )}
                    {!authorMeta && requiredAt === "finalize" && (
                      <span
                        style={{
                          fontSize: 9.5,
                          color: "var(--c-warn)",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                        }}
                      >
                        {t("projectSettings.metaForSubmission")}
                      </span>
                    )}
                  </label>
                  {def.type === "select" && options.length > 0 ? (
                    <select
                      className="input"
                      value={value}
                      onChange={(e) => {
                        setValue(e.target.value, true);
                      }}
                    >
                      <option value="">
                        {authorMeta ? inheritedLabel : "—"}
                      </option>
                      {options.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      className="input"
                      value={value}
                      placeholder={
                        authorMeta
                          ? sharedValue || (def.placeholder ?? "")
                          : (def.placeholder ?? "")
                      }
                      onChange={(e) => {
                        setValue(e.target.value, false);
                      }}
                    />
                  )}
                  {authorMeta && blank && (
                    <div className="hint dim">
                      {t("projectSettings.metaInherited")}
                    </div>
                  )}
                  {authorMeta && !blank && (
                    <button
                      type="button"
                      className="hint"
                      style={{
                        background: "none",
                        border: "none",
                        padding: 0,
                        cursor: "pointer",
                        textAlign: "left",
                        color: "var(--accent)",
                      }}
                      onClick={() => {
                        setValue("", true);
                      }}
                    >
                      {t("projectSettings.metaResetToShared")}
                    </button>
                  )}
                  {!authorMeta && blank && requiredAt !== "never" && (
                    <div
                      className="hint"
                      style={{
                        color:
                          requiredAt === "create"
                            ? "var(--c-err)"
                            : "var(--c-warn)",
                      }}
                    >
                      {requiredAt === "create"
                        ? t("projectSettings.metaRequired")
                        : t("projectSettings.metaRequiredForSubmission")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </SectionCard>
  );
};
