import { useState } from "react";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  PackSubmission,
  PackSubmissionExtra,
  PackSubmissionItem,
  PackSubmissionOp,
  PackSubmissionProfile,
  PackSubmissionSlot,
} from "@entities/pack-studio";
import { Button, Input, Select } from "@shared/ui";
import {
  SIGN_METHODS,
  WHEN_KEYS,
  kindsKey,
  kindsOf,
  pointSlots,
  profileDocs,
  slotsFor,
  toggleMethod,
  toggleSignature,
  whenFromKey,
  whenKey,
} from "../lib/submission";
import { BlockHead, Check } from "./kit";
import { useWhenText } from "../lib/whenText";

/** Что нужно редакторам записей: модель версии, запись правок и подписи. */
export type FormCtx = {
  data: PackSubmission;
  disabled: boolean;
  apply: (ops: PackSubmissionOp[]) => void;
  slotLabel: (slot: string) => string;
  docName: (doc: string) => string;
};

type ListName = "items" | "extra_items" | "signing_slots";

const entryOps = (profile: number, entries: ListName) => ({
  move: (index: number, to: number): PackSubmissionOp => ({
    op: "move_entry",
    profile,
    entries,
    index,
    to,
  }),
  remove: (index: number): PackSubmissionOp => ({
    op: "remove_entry",
    profile,
    entries,
    index,
  }),
});

/** Стрелки и корзина записи списка. */
const RowActions = ({
  ctx,
  profile,
  entries,
  index,
  count,
  label,
}: {
  ctx: FormCtx;
  profile: number;
  entries: ListName;
  index: number;
  count: number;
  label: string;
}) => {
  const { t } = useTranslation("packStudio");
  const ops = entryOps(profile, entries);
  return (
    <span className="psf-actions">
      <button
        type="button"
        className="icon-btn"
        disabled={ctx.disabled || index === 0}
        onClick={() => {
          ctx.apply([ops.move(index, index - 1)]);
        }}
        aria-label={t("submission.up", { what: label })}
        title={t("submission.up", { what: label })}
      >
        <ChevronUp size="0.75rem" />
      </button>
      <button
        type="button"
        className="icon-btn"
        disabled={ctx.disabled || index >= count - 1}
        onClick={() => {
          ctx.apply([ops.move(index, index + 1)]);
        }}
        aria-label={t("submission.down", { what: label })}
        title={t("submission.down", { what: label })}
      >
        <ChevronDown size="0.75rem" />
      </button>
      <button
        type="button"
        className="icon-btn"
        disabled={ctx.disabled}
        onClick={() => {
          ctx.apply([ops.remove(index)]);
        }}
        aria-label={t("submission.remove", { what: label })}
        title={t("submission.remove", { what: label })}
        data-testid={`p${String(profile)}-remove-${entries}-${String(index)}`}
      >
        <Trash2 size="0.75rem" />
      </button>
    </span>
  );
};

const BrokenRow = ({ error }: { error: string | null }) => {
  const { t } = useTranslation("packStudio");
  return (
    <p className="hint psf-warn">
      {t("submission.brokenEntry", { error: error ?? "" })}
    </p>
  );
};

const KindsSelect = ({
  value,
  onChange,
  disabled,
  label,
}: {
  value: readonly string[];
  onChange: (kinds: ("research" | "project")[]) => void;
  disabled: boolean;
  label: string;
}) => {
  const { t } = useTranslation("packStudio");
  return (
    <Select
      value={kindsKey(value)}
      onValueChange={(key) => {
        onChange(kindsOf(key));
      }}
      isDisabled={disabled}
      ariaLabel={label}
      options={(["both", "research", "project"] as const).map((key) => ({
        value: key,
        label: t(`submission.kinds.${key}`),
      }))}
    />
  );
};

// ── пункты ──────────────────────────────────────────────────────────────────

const ItemRow = ({
  ctx,
  profile,
  index,
  count,
  item,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
  index: number;
  count: number;
  item: PackSubmissionItem;
}) => {
  const { t } = useTranslation("packStudio");
  const set = (next: PackSubmissionItem) => {
    ctx.apply([
      {
        op: "set_entry",
        profile: profile.index,
        entries: "items",
        index,
        item: next,
      },
    ]);
  };
  const slots = slotsFor(ctx.data, item.doc_id);
  const docs = ctx.data.documents.includes(item.doc_id)
    ? ctx.data.documents
    : [item.doc_id, ...ctx.data.documents];
  const unknown = item.signatures.filter(
    (slot) => !slots.some((s) => s.id === slot),
  );
  return (
    <li
      className="psf-row"
      data-testid={`p${String(profile.index)}-item-${String(index)}`}
      data-pf-at={`/pack_submission/profiles/${String(profile.index)}/items/${String(index)}`}
    >
      <div className="psf-row-head">
        <Select
          value={item.doc_id}
          onValueChange={(doc) => {
            set({ ...item, doc_id: doc, signatures: [], methods: {} });
          }}
          isDisabled={ctx.disabled}
          ariaLabel={t("submission.items.document")}
          options={docs.map((doc) => ({
            value: doc,
            label: `${ctx.docName(doc)} (${doc})`,
          }))}
        />
        <RowActions
          ctx={ctx}
          profile={profile.index}
          entries="items"
          index={index}
          count={count}
          label={ctx.docName(item.doc_id)}
        />
      </div>
      <div className="psf-sign-grid">
        {slots.length === 0 && (
          <p className="hint">{t("submission.items.noSlots")}</p>
        )}
        {slots.map((slot) => {
          const on = item.signatures.includes(slot.id);
          const methods = item.methods[slot.id] ?? [];
          return (
            <div className="psf-sign" key={slot.id}>
              <Check
                label={ctx.slotLabel(slot.id)}
                checked={on}
                disabled={ctx.disabled}
                onChange={(next) => {
                  set(toggleSignature(item, slot.id, next));
                }}
                testId={`p${String(profile.index)}-item-${String(index)}-sign-${slot.id}`}
              />
              {on && (
                <span className="psf-methods">
                  {SIGN_METHODS.map((method) => (
                    <Check
                      key={method}
                      label={t(`submission.method.${method}`)}
                      checked={methods.includes(method)}
                      disabled={ctx.disabled}
                      onChange={(next) => {
                        set(toggleMethod(item, slot.id, method, next));
                      }}
                      testId={`p${String(profile.index)}-item-${String(index)}-method-${slot.id}-${method}`}
                    />
                  ))}
                  {methods.length === 0 && (
                    <span className="hint">{t("submission.method.any")}</span>
                  )}
                </span>
              )}
            </div>
          );
        })}
        {unknown.length > 0 && (
          <p className="hint psf-warn">
            {t("submission.items.unknownSlots", { slots: unknown.join(", ") })}
          </p>
        )}
      </div>
      <div className="psf-row-foot">
        {ctx.data.has_nda && (
          <Check
            label={t("submission.items.skipIfNda")}
            checked={item.skip_if_nda}
            disabled={ctx.disabled}
            onChange={(next) => {
              set({ ...item, skip_if_nda: next });
            }}
          />
        )}
        <span className="psf-inline-field">
          <span className="hint">{t("submission.kinds.label")}</span>
          <KindsSelect
            value={item.supported_kinds}
            disabled={ctx.disabled}
            label={t("submission.kinds.label")}
            onChange={(kinds) => {
              set({ ...item, supported_kinds: kinds });
            }}
          />
        </span>
      </div>
    </li>
  );
};

export const ItemsEditor = ({
  ctx,
  profile,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
}) => {
  const { t } = useTranslation("packStudio");
  const [doc, setDoc] = useState("");
  return (
    <section
      className="psf-block"
      data-testid={`items-${String(profile.index)}`}
    >
      <BlockHead
        title={t("submission.items.title")}
        hint={t("submission.items.hint")}
      />
      <ul className="psf-rows">
        {profile.items.map((entry) =>
          entry.entry ? (
            <ItemRow
              key={entry.index}
              ctx={ctx}
              profile={profile}
              index={entry.index}
              count={profile.items.length}
              item={entry.entry}
            />
          ) : (
            <li key={entry.index} className="psf-row">
              <BrokenRow error={entry.error} />
            </li>
          ),
        )}
      </ul>
      <div className="psf-add">
        <Select
          value={doc}
          onValueChange={setDoc}
          isDisabled={ctx.disabled}
          placeholder={t("submission.items.addPlaceholder")}
          ariaLabel={t("submission.items.addPlaceholder")}
          options={ctx.data.documents.map((id) => ({
            value: id,
            label: `${ctx.docName(id)} (${id})`,
          }))}
        />
        <Button
          size="xs"
          variant="secondary"
          disabled={ctx.disabled || doc === ""}
          onClick={() => {
            ctx.apply([
              {
                op: "add_entry",
                profile: profile.index,
                entries: "items",
                item: {
                  doc_id: doc,
                  signatures: [],
                  methods: {},
                  skip_if_nda: false,
                  supported_kinds: [],
                },
              },
            ]);
            setDoc("");
          }}
          data-testid={`items-${String(profile.index)}-add`}
        >
          <Plus size="0.6875rem" />
          {t("submission.items.add")}
        </Button>
      </div>
    </section>
  );
};

// ── файлы сверх документов ──────────────────────────────────────────────────

const OTHER = "__other__";

const ExtraRow = ({
  ctx,
  profile,
  index,
  count,
  extra,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
  index: number;
  count: number;
  extra: PackSubmissionExtra;
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const [draft, setDraft] = useState(extra);
  const [seen, setSeen] = useState(extra);
  if (seen !== extra) {
    setSeen(extra);
    setDraft(extra);
  }
  const form = ctx.data.forms.find((f) => f.source === extra.source);
  const set = (next: PackSubmissionExtra) => {
    if (JSON.stringify(next) === JSON.stringify(extra)) return;
    ctx.apply([
      {
        op: "set_entry",
        profile: profile.index,
        entries: "extra_items",
        index,
        extra: next,
      },
    ]);
  };
  const title = form
    ? (form.title[i18n.language] ?? form.title.ru ?? form.id)
    : extra.source;
  return (
    <li
      className="psf-row"
      data-testid={`p${String(profile.index)}-extra-${String(index)}`}
      data-pf-at={`/pack_submission/profiles/${String(profile.index)}/extra_items/${String(index)}`}
    >
      <div className="psf-row-head">
        <span className="psf-row-title">
          {form ? t("submission.extras.form", { title }) : extra.source}
        </span>
        <RowActions
          ctx={ctx}
          profile={profile.index}
          entries="extra_items"
          index={index}
          count={count}
          label={title}
        />
      </div>
      <div className="psf-row-fields">
        {!form && (
          <Input
            label={t("submission.extras.source")}
            value={draft.source}
            isMono
            disabled={ctx.disabled}
            onChange={(e) => {
              setDraft({ ...draft, source: e.target.value });
            }}
            onBlur={() => {
              if (draft.source.trim()) set(draft);
            }}
          />
        )}
        <Input
          label={t("submission.extras.outputName")}
          value={draft.output_name}
          disabled={ctx.disabled}
          onChange={(e) => {
            setDraft({ ...draft, output_name: e.target.value });
          }}
          onBlur={() => {
            set(draft);
          }}
        />
        <Input
          label={t("submission.extras.format")}
          value={draft.format ?? ""}
          isMono
          disabled={ctx.disabled}
          onChange={(e) => {
            setDraft({ ...draft, format: e.target.value || null });
          }}
          onBlur={() => {
            set(draft);
          }}
        />
        <span className="psf-inline-field">
          <span className="hint">{t("submission.kinds.label")}</span>
          <KindsSelect
            value={extra.supported_kinds}
            disabled={ctx.disabled}
            label={t("submission.kinds.label")}
            onChange={(kinds) => {
              set({ ...draft, supported_kinds: kinds });
            }}
          />
        </span>
      </div>
      {form && !form.required_for_pack && (
        <p className="hint psf-warn" data-testid="extra-not-required">
          {t("submission.extras.notRequired", { form: title })}
        </p>
      )}
    </li>
  );
};

export const ExtrasEditor = ({
  ctx,
  profile,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
}) => {
  const { t, i18n } = useTranslation("packStudio");
  const [source, setSource] = useState("");
  const add = () => {
    const form = ctx.data.forms.find((f) => f.id === source);
    const extra: PackSubmissionExtra = form
      ? {
          source: form.source,
          output_name: form.output_name,
          format: form.format,
          supported_kinds: [],
        }
      : {
          source: ".hse-studio/",
          output_name: "",
          format: null,
          supported_kinds: [],
        };
    ctx.apply([
      {
        op: "add_entry",
        profile: profile.index,
        entries: "extra_items",
        extra,
      },
    ]);
    setSource("");
  };
  return (
    <section
      className="psf-block"
      data-testid={`extras-${String(profile.index)}`}
    >
      <BlockHead
        title={t("submission.extras.title")}
        hint={t("submission.extras.hint")}
      />
      {profile.extra_items.length > 0 && (
        <ul className="psf-rows">
          {profile.extra_items.map((entry) =>
            entry.entry ? (
              <ExtraRow
                key={entry.index}
                ctx={ctx}
                profile={profile}
                index={entry.index}
                count={profile.extra_items.length}
                extra={entry.entry}
              />
            ) : (
              <li key={entry.index} className="psf-row">
                <BrokenRow error={entry.error} />
              </li>
            ),
          )}
        </ul>
      )}
      <div className="psf-add">
        <Select
          value={source}
          onValueChange={setSource}
          isDisabled={ctx.disabled}
          placeholder={t("submission.extras.addPlaceholder")}
          ariaLabel={t("submission.extras.addPlaceholder")}
          options={[
            ...ctx.data.forms.map((f) => ({
              value: f.id,
              label: t("submission.extras.form", {
                title: f.title[i18n.language] ?? f.title.ru ?? f.id,
              }),
            })),
            { value: OTHER, label: t("submission.extras.other") },
          ]}
        />
        <Button
          size="xs"
          variant="secondary"
          disabled={ctx.disabled || source === ""}
          onClick={add}
          data-testid={`extras-${String(profile.index)}-add`}
        >
          <Plus size="0.6875rem" />
          {t("submission.extras.add")}
        </Button>
      </div>
    </section>
  );
};

// ── пресет точки: signing_slots ─────────────────────────────────────────────

const SlotRow = ({
  ctx,
  profile,
  index,
  count,
  entry,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
  index: number;
  count: number;
  entry: PackSubmissionSlot;
}) => {
  const { t } = useTranslation("packStudio");
  const whenText = useWhenText();
  const docs = profileDocs(profile);
  const docOptions = docs.includes(entry.doc_id)
    ? docs
    : [entry.doc_id, ...docs];
  const slots = slotsFor(ctx.data, entry.doc_id);
  const slotIds = slots.some((s) => s.id === entry.slot_id)
    ? slots.map((s) => s.id)
    : [entry.slot_id, ...slots.map((s) => s.id)];
  const ofPoint = pointSlots(profile, entry.doc_id).has(entry.slot_id);
  const required =
    ctx.data.slots.find((s) => s.id === entry.slot_id)?.required ?? false;
  const set = (next: PackSubmissionSlot) => {
    ctx.apply([
      {
        op: "set_entry",
        profile: profile.index,
        entries: "signing_slots",
        index,
        slot: next,
      },
    ]);
  };
  return (
    <li
      className="psf-row psf-slot-row"
      data-testid={`p${String(profile.index)}-preset-${String(index)}`}
      data-pf-at={`/pack_submission/profiles/${String(profile.index)}/signing_slots/${String(index)}`}
    >
      <div className="psf-row-fields">
        <Select
          value={entry.doc_id}
          onValueChange={(doc) => {
            const first = slotsFor(ctx.data, doc)[0]?.id ?? entry.slot_id;
            set({ ...entry, doc_id: doc, slot_id: first });
          }}
          isDisabled={ctx.disabled}
          ariaLabel={t("submission.preset.document")}
          options={docOptions.map((doc) => ({
            value: doc,
            label: ctx.docName(doc),
          }))}
        />
        <Select
          value={entry.slot_id}
          onValueChange={(slot) => {
            const point = pointSlots(profile, entry.doc_id).has(slot);
            set({ ...entry, slot_id: slot, when: point ? null : entry.when });
          }}
          isDisabled={ctx.disabled}
          ariaLabel={t("submission.preset.slot")}
          options={slotIds.map((slot) => ({
            value: slot,
            label: ctx.slotLabel(slot),
          }))}
        />
        <Select
          value={whenKey(entry.when)}
          onValueChange={(key) => {
            set({ ...entry, when: whenFromKey(key) });
          }}
          isDisabled={ctx.disabled || ofPoint}
          ariaLabel={t("submission.preset.when")}
          options={WHEN_KEYS.map((key) => ({
            value: key,
            label: whenText(whenFromKey(key)),
          }))}
        />
        <Check
          label={t("submission.preset.optional")}
          checked={entry.optional}
          disabled={ctx.disabled || required}
          title={required ? t("submission.preset.requiredSlot") : undefined}
          onChange={(next) => {
            set({ ...entry, optional: next });
          }}
          testId={`p${String(profile.index)}-preset-${String(index)}-optional`}
        />
        <RowActions
          ctx={ctx}
          profile={profile.index}
          entries="signing_slots"
          index={index}
          count={count}
          label={ctx.slotLabel(entry.slot_id)}
        />
      </div>
      <p className="hint">
        {ofPoint
          ? t("submission.preset.ofPoint")
          : t("submission.preset.extra", { when: whenText(entry.when) })}
      </p>
    </li>
  );
};

export const PresetEditor = ({
  ctx,
  profile,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
}) => {
  const { t } = useTranslation("packStudio");
  const docs = profileDocs(profile);
  const [doc, setDoc] = useState("");
  const [slot, setSlot] = useState("");
  const chosenDoc = doc !== "" ? doc : (docs[0] ?? "");
  const slots = chosenDoc ? slotsFor(ctx.data, chosenDoc) : [];
  const chosenSlot = slots.some((s) => s.id === slot)
    ? slot
    : (slots[0]?.id ?? "");
  return (
    <section
      className="psf-block"
      data-testid={`preset-${String(profile.index)}`}
    >
      <BlockHead
        title={t("submission.preset.title")}
        hint={t("submission.preset.hint")}
      />
      {profile.signing_slots.length > 0 && (
        <ul className="psf-rows">
          {profile.signing_slots.map((entry) =>
            entry.entry ? (
              <SlotRow
                key={entry.index}
                ctx={ctx}
                profile={profile}
                index={entry.index}
                count={profile.signing_slots.length}
                entry={entry.entry}
              />
            ) : (
              <li key={entry.index} className="psf-row">
                <BrokenRow error={entry.error} />
              </li>
            ),
          )}
        </ul>
      )}
      {docs.length === 0 ? (
        <p className="hint">{t("submission.preset.noItems")}</p>
      ) : (
        <div className="psf-add">
          <Select
            value={chosenDoc}
            onValueChange={setDoc}
            isDisabled={ctx.disabled}
            ariaLabel={t("submission.preset.document")}
            options={docs.map((d) => ({ value: d, label: ctx.docName(d) }))}
          />
          <Select
            value={chosenSlot}
            onValueChange={setSlot}
            isDisabled={ctx.disabled || slots.length === 0}
            ariaLabel={t("submission.preset.slot")}
            options={slots.map((s) => ({
              value: s.id,
              label: ctx.slotLabel(s.id),
            }))}
          />
          <Button
            size="xs"
            variant="secondary"
            disabled={ctx.disabled || chosenSlot === ""}
            onClick={() => {
              ctx.apply([
                {
                  op: "add_entry",
                  profile: profile.index,
                  entries: "signing_slots",
                  slot: {
                    doc_id: chosenDoc,
                    slot_id: chosenSlot,
                    when: null,
                    optional: false,
                  },
                },
              ]);
              setSlot("");
            }}
            data-testid={`preset-${String(profile.index)}-add`}
          >
            <Plus size="0.6875rem" />
            {t("submission.preset.add")}
          </Button>
        </div>
      )}
    </section>
  );
};
