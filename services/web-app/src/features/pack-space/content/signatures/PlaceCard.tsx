import { ArrowRight, Link2, Link2Off, Pin, Star, Undo2 } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type {
  PackPlaceOp,
  PackSignatures,
  PackSignatureSlot,
} from "@entities/pack-studio";
import {
  bindingOf,
  dateOpFrom,
  freeDateAnchors,
  marksBefore,
  placeholderHeightMm,
  placementOf,
} from "@features/pack-places";
import { SlotDateMarks } from "@features/signature-stamper";
import { pickLocalized } from "@shared/lib";
import { Button } from "@shared/ui";
import { entryKind, entryPage, mm, placeStatusOf } from "./words";

// Карточка одной подписи в документе (pack-studio-ux.md, 5.5, S8c): где она стоит словами и что с
// ней можно сделать. Слов «слот» и «якорь» нет: «подпись», «место», «следует за текстом».

export type PlaceCardProps = {
  slot: PackSignatureSlot;
  data: PackSignatures;
  document: string;
  /** Страница, открытая на просмотре. */
  page: number;
  pageCount: number;
  lang: string;
  editable: boolean;
  pending: boolean;
  onOp: (op: PackPlaceOp | null) => void;
  onJump: (page: number) => void;
};

export const PlaceCard = ({
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
}: PlaceCardProps) => {
  const { t, i18n } = useTranslation("packSpace");
  const frame = slot.document;
  if (!frame) return null;
  const box = frame.box;
  const status = placeStatusOf(slot) ?? "missing";
  const binding = bindingOf(slot);
  const label = pickLocalized(slot.label, i18n.language, slot.id);
  const op = (fields: Omit<PackPlaceOp, "slot" | "doc">) => {
    onOp({ slot: slot.id, doc: document, ...fields });
  };
  // Строка даты называется по виду даты («day», «month_word»): слова те же, что у формата метки.
  const dateLine = (name: string): string =>
    i18n.exists(`signatureStamper:dates.formats.${name}`)
      ? t(`signatureStamper:dates.formats.${name}`)
      : name;
  const missingDates = frame.dates.filter((date) => date.box === null);
  const lines = freeDateAnchors(slot, data.build?.date_anchors ?? []);
  const canFollow =
    binding === "mm" &&
    box !== null &&
    (data.build?.sign_anchors ?? []).includes(slot.id);
  const key = `places-${slot.id}`;

  return (
    <li
      className={clsx("sp-ct-sg-card", `is-${status}`)}
      data-testid={key}
      data-status={status}
    >
      <div className="sp-ct-sg-head">
        <b className="sp-ct-sg-name">{label}</b>
        {slot.required && (
          <span className="sp-ct-sg-chip">
            {t("content.signatures.required")}
          </span>
        )}
        {slot.per_author && (
          <span className="sp-ct-sg-chip">
            {t("content.signatures.perAuthor")}
          </span>
        )}
      </div>

      <p
        className={clsx("sp-ct-sg-status", status === "missing" && "warn")}
        data-testid={`${key}-status`}
      >
        {status === "own" && t("content.signatures.own", { page: box?.page })}
        {status === "shared" &&
          t("content.signatures.shared", { page: box?.page })}
        {status === "missing" && t("content.signatures.missing")}
      </p>
      {status === "shared" && (
        <p className="sp-ct-sg-note">{t("content.signatures.sharedNote")}</p>
      )}
      {binding !== "mm" && (
        <p
          className={clsx("sp-ct-sg-note", binding !== "line" && "warn")}
          data-testid={`${key}-follow`}
        >
          {t(`content.signatures.follow.${binding}`)}
        </p>
      )}

      {box && box.page !== page && (
        <div className="sp-ct-sg-row">
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              onJump(box.page);
            }}
          >
            <ArrowRight size="0.625rem" aria-hidden="true" />
            {t("content.signatures.jump", { page: box.page })}
          </Button>
        </div>
      )}

      {editable && (
        <div className="sp-ct-sg-row">
          {box?.page !== page && (
            <Button
              size="xs"
              variant="secondary"
              disabled={pending || pageCount === 0}
              data-testid={`${key}-here`}
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
              {t("content.signatures.placeHere", { page })}
            </Button>
          )}
          {frame.kind === "place" && (
            <>
              <Button
                size="xs"
                variant="ghost"
                disabled={pending}
                title={t("content.signatures.makeSharedHint")}
                data-testid={`${key}-shared`}
                onClick={() => {
                  op({ op: "make_default" });
                }}
              >
                <Star size="0.625rem" aria-hidden="true" />
                {t("content.signatures.makeShared")}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                disabled={pending}
                title={t("content.signatures.useSharedHint")}
                data-testid={`${key}-useshared`}
                onClick={() => {
                  op({ op: "remove_place" });
                }}
              >
                <Undo2 size="0.625rem" aria-hidden="true" />
                {t("content.signatures.useShared")}
              </Button>
            </>
          )}
          {canFollow && (
            <Button
              size="xs"
              variant="ghost"
              disabled={pending}
              title={t("content.signatures.followHint")}
              data-testid={`${key}-follow-on`}
              onClick={() => {
                op({ op: "bind_anchor" });
              }}
            >
              <Link2 size="0.625rem" aria-hidden="true" />
              {t("content.signatures.followOn")}
            </Button>
          )}
          {(binding === "line" || binding === "fallback") && (
            <Button
              size="xs"
              variant="ghost"
              disabled={pending}
              title={t("content.signatures.followOffHint")}
              data-testid={`${key}-follow-off`}
              onClick={() => {
                op({ op: "unbind_anchor" });
              }}
            >
              <Link2Off size="0.625rem" aria-hidden="true" />
              {t("content.signatures.followOff")}
            </Button>
          )}
        </div>
      )}

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
          className="sp-ct-sg-row warn"
          data-testid={`${key}-date-missing-${String(date.index)}`}
        >
          <span>{t("content.signatures.dateMissing")}</span>
          {editable && (
            <Button
              size="xs"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                op({ op: "remove_date", index: date.index });
              }}
            >
              {t("content.signatures.dateRemove")}
            </Button>
          )}
        </div>
      ))}
      {editable && lines.length > 0 && (
        <div className="sp-ct-sg-row">
          <span className="sp-ct-sg-note">
            {t("content.signatures.dateLines")}
          </span>
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
              {dateLine(anchor.slice(slot.id.length + 1))}
            </Button>
          ))}
        </div>
      )}

      <details className="sp-ct-sg-more">
        <summary>{t("content.signatures.details")}</summary>
        <dl>
          <dt>{t("content.signatures.exact")}</dt>
          <dd>
            {box
              ? t("content.signatures.exactBox", {
                  page: box.page,
                  x: mm(box.x_mm),
                  y: mm(box.y_mm),
                  width: mm(box.width_mm),
                })
              : t("content.signatures.exactNone")}
          </dd>
          <dt>{t("content.signatures.common")}</dt>
          <dd>
            {entryKind(slot.default_place) === "page"
              ? t("content.signatures.commonPage", {
                  page: entryPage(slot.default_place),
                })
              : t("content.signatures.commonText")}
            {!slot.default_set && ` ${t("content.signatures.commonLoader")}`}
          </dd>
          <dt>{t("content.signatures.code")}</dt>
          <dd>
            <code className="mono">{slot.id}</code>
          </dd>
        </dl>
      </details>
    </li>
  );
};
