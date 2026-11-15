import { ArrowRight, Link2, Link2Off, Pin, Star, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  PackPlaceEntry,
  PackPlaceOp,
  PackSignatures,
  PackSignatureSlot,
} from "@entities/pack-studio";
import { SlotDateMarks } from "@features/signature-stamper";
import { pickLocalized } from "@shared/lib";
import { Button } from "@shared/ui";
import {
  bindingOf,
  dateOpFrom,
  freeDateAnchors,
  marksBefore,
  placeholderHeightMm,
  placementOf,
  type Binding,
} from "../lib/placesState";

export type SlotCatalogProps = {
  data: PackSignatures;
  document: string;
  page: number;
  pageCount: number;
  /** Язык документа: месяц в примере метки даты. */
  lang: string;
  editable: boolean;
  pending: boolean;
  onOp: (op: PackPlaceOp | null) => void;
  onJump: (page: number) => void;
};

const mm = (value: number): string => String(Math.round(value * 10) / 10);

const BINDING_MARK: Record<Binding, string> = {
  line: "ps-mark ps-mark-ok",
  fallback: "ps-mark ps-mark-warn",
  missing: "ps-mark ps-mark-warn",
  mm: "ps-mark",
};

/** Запись места словами: «стр. 1, 110 и 130 мм, ширина 40» или «по строке supervisor». */
const useEntryText = () => {
  const { t } = useTranslation("packStudio");
  return (entry: PackPlaceEntry): string =>
    entry.source === "mm"
      ? t("places.entryMm", {
          page: entry.page,
          x: mm(entry.x_mm),
          y: mm(entry.y_mm),
          width: mm(entry.width_mm),
        })
      : t("places.entryAnchor", { anchor: entry.anchor });
};

const SlotCard = ({
  slot,
  data,
  document,
  page,
  pageCount,
  lang,
  editable,
  pending,
  onOp,
  onJump,
}: SlotCatalogProps & { slot: PackSignatureSlot }) => {
  const { t, i18n } = useTranslation("packStudio");
  const entryText = useEntryText();
  const frame = slot.document;
  if (!frame) return null;
  const box = frame.box;
  const binding = bindingOf(slot);
  const signAnchors = data.build?.sign_anchors ?? [];
  const missingDates = frame.dates.filter((date) => date.box === null);
  const lines = freeDateAnchors(slot, data.build?.date_anchors ?? []);
  const label = pickLocalized(slot.label, i18n.language, slot.id);
  const op = (fields: Omit<PackPlaceOp, "slot" | "doc">) => {
    onOp({ slot: slot.id, doc: document, ...fields });
  };

  return (
    <li className="ps-slot" data-testid={`places-slot-${slot.id}`}>
      <div className="ps-slot-head">
        <span className="ps-slot-name">{label}</span>
        <code className="mono ps-slot-id">{slot.id}</code>
      </div>
      <div className="ps-slot-marks">
        <span
          className={
            frame.kind === "place" ? "ps-mark ps-mark-info" : "ps-mark"
          }
          data-testid={`places-kind-${slot.id}`}
        >
          {t(`places.kind.${frame.kind}`)}
        </span>
        <span
          className={BINDING_MARK[binding]}
          data-testid={`places-binding-${slot.id}`}
        >
          {t(`places.binding.${binding}`, { anchor: frame.anchor?.id ?? "" })}
        </span>
        {slot.per_author && (
          <span className="ps-mark">{t("places.perAuthor")}</span>
        )}
        {slot.required && (
          <span className="ps-mark">{t("places.required")}</span>
        )}
      </div>
      <div className="ps-slot-where">
        <span>
          {box
            ? t("places.where", {
                page: box.page,
                x: mm(box.x_mm),
                y: mm(box.y_mm),
                width: mm(box.width_mm),
              })
            : t("places.noBox")}
        </span>
        {box && box.page !== page && (
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              onJump(box.page);
            }}
          >
            <ArrowRight size="0.625rem" aria-hidden="true" />
            {t("places.jump")}
          </Button>
        )}
      </div>
      {editable && (
        <div className="ps-slot-actions">
          {box?.page !== page && (
            <Button
              size="xs"
              variant="secondary"
              disabled={pending || pageCount === 0}
              data-testid={`places-here-${slot.id}`}
              onClick={() => {
                op({
                  op: "set_place",
                  box: {
                    page,
                    x_mm: box?.x_mm ?? 90,
                    y_mm: box?.y_mm ?? 140,
                    width_mm: box?.width_mm ?? 40,
                  },
                });
              }}
            >
              <Pin size="0.625rem" aria-hidden="true" />
              {t("places.placeHere", { page })}
            </Button>
          )}
          {frame.kind === "place" && (
            <>
              <Button
                size="xs"
                variant="ghost"
                disabled={pending}
                title={t("places.makeDefaultHint")}
                data-testid={`places-default-${slot.id}`}
                onClick={() => {
                  op({ op: "make_default" });
                }}
              >
                <Star size="0.625rem" aria-hidden="true" />
                {t("places.makeDefault")}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                disabled={pending}
                title={t("places.removeHint")}
                data-testid={`places-remove-${slot.id}`}
                onClick={() => {
                  op({ op: "remove_place" });
                }}
              >
                <Trash2 size="0.625rem" aria-hidden="true" />
                {t("places.remove")}
              </Button>
            </>
          )}
          {binding === "mm" &&
            box !== null &&
            signAnchors.includes(slot.id) && (
              <Button
                size="xs"
                variant="ghost"
                disabled={pending}
                title={t("places.bindHint")}
                data-testid={`places-bind-${slot.id}`}
                onClick={() => {
                  op({ op: "bind_anchor" });
                }}
              >
                <Link2 size="0.625rem" aria-hidden="true" />
                {t("places.bind")}
              </Button>
            )}
          {(binding === "line" || binding === "fallback") && (
            <Button
              size="xs"
              variant="ghost"
              disabled={pending}
              title={t("places.unbindHint")}
              data-testid={`places-unbind-${slot.id}`}
              onClick={() => {
                op({ op: "unbind_anchor" });
              }}
            >
              <Link2Off size="0.625rem" aria-hidden="true" />
              {t("places.unbind")}
            </Button>
          )}
        </div>
      )}
      <p className="ps-slot-default">
        {t("places.defaultPlace", { place: entryText(slot.default_place) })}
        {!slot.default_set && ` ${t("places.defaultLoader")}`}
      </p>
      <SlotDateMarks
        slotId={slot.id}
        placement={placementOf(slot)}
        lang={lang}
        currentPage={page}
        pageCount={pageCount}
        signatureHeightMm={placeholderHeightMm(box?.width_mm ?? 40)}
        signerName={label}
        route={null}
        editable={editable}
        pending={pending}
        onSave={(save) => {
          onOp(dateOpFrom(slot.id, document, marksBefore(slot), save));
        }}
        onJumpToPage={onJump}
        indent={false}
        showSignedAt={false}
      />
      {missingDates.map((date) => (
        <div
          key={date.index}
          className="ps-slot-missing"
          data-testid={`places-date-missing-${slot.id}-${String(date.index)}`}
        >
          <span>
            {t("places.dateMissing", {
              anchor: date.entry.source === "anchor" ? date.entry.anchor : "",
            })}
          </span>
          {editable && (
            <Button
              size="xs"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                op({ op: "remove_date", index: date.index });
              }}
            >
              <Trash2 size="0.625rem" aria-hidden="true" />
              {t("places.dateRemove")}
            </Button>
          )}
        </div>
      ))}
      {editable && lines.length > 0 && (
        <div className="ps-slot-lines">
          <span className="ps-slot-hint">{t("places.dateLines")}</span>
          {lines.map((anchor) => (
            <Button
              key={anchor}
              size="xs"
              variant="secondary"
              disabled={pending}
              data-testid={`places-line-${anchor}`}
              onClick={() => {
                op({ op: "add_date", anchor });
              }}
            >
              {anchor.slice(slot.id.length + 1)}
            </Button>
          ))}
        </div>
      )}
    </li>
  );
};

/**
 * Каталог слотов версии у документа сборки: место каждого слота (своё или по умолчанию, на строке
 * шаблона или в мм), действия над ним и метки даты. Слоты, которые к документу не относятся, ниже
 * списком.
 */
export const SlotCatalog = (props: SlotCatalogProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const applicable = props.data.slots.filter((slot) => slot.document !== null);
  const others = props.data.slots.filter((slot) => slot.document === null);
  return (
    <div className="ps-slots" data-testid="places-catalog">
      {applicable.length === 0 ? (
        <p className="ps-pane-empty">{t("places.noSlots")}</p>
      ) : (
        <ul className="ps-slot-list">
          {applicable.map((slot) => (
            <SlotCard key={slot.id} {...props} slot={slot} />
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <details className="sync-details">
          <summary>{t("places.others", { count: others.length })}</summary>
          <ul className="ps-slot-others">
            {others.map((slot) => (
              <li key={slot.id}>
                <span>{pickLocalized(slot.label, i18n.language, slot.id)}</span>{" "}
                <span className="ps-slot-hint">
                  {t("places.appliesTo", { docs: slot.applies_to.join(", ") })}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
};
