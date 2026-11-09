import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Crosshair, ExternalLink } from "lucide-react";
import { pickLocalized } from "@shared/lib";
import { Badge, Button, PageTabs, PdfViewer } from "@shared/ui";
import type {
  SigningTask,
  SigningTaskDoc,
  SigningTaskSlot,
} from "@entities/signing-route";
import {
  jumpToSlot,
  myFrames,
  pendingMine,
  type PdfJumpTarget,
} from "../lib/signingState";

export type SigningDocsProps = {
  task: SigningTask;
  /** Адрес PDF документа: по умолчанию `pdf_url` задачи; галерея подставляет образец. */
  pdfUrlOf: (doc: SigningTaskDoc) => string;
};

const slotStatusKey = (slot: SigningTaskSlot): string =>
  slot.status === "pending" && slot.reason === "awaiting_approval"
    ? "awaiting"
    : slot.status;

/**
 * Документы маршрута вкладками: PDF с рамками своих слотов («Ваша подпись»), кнопка
 * «К месту подписи» и список своих и чужих подписей документа (раздел 3.2).
 */
export const SigningDocs = ({ task, pdfUrlOf }: SigningDocsProps) => {
  const { t, i18n } = useTranslation("signing");
  const [selected, setSelected] = useState<string | null>(null);
  const [jump, setJump] = useState<PdfJumpTarget | null>(null);
  // Сколько раз нажали «К месту подписи»: следующее нажатие ведёт к следующему слоту.
  const [presses, setPresses] = useState(0);
  const viewerRef = useRef<HTMLDivElement | null>(null);

  const doc =
    task.docs.find((d) => d.doc_id === selected) ?? task.docs[0] ?? null;

  if (!doc) {
    return (
      <section className="sgn-docs" data-testid="signing-docs">
        <p className="sgn-others">{t("docs.empty")}</p>
      </section>
    );
  }

  const name = (d: SigningTaskDoc) =>
    pickLocalized(d.name, i18n.language, d.doc_id);
  const goTo = (slot: SigningTaskSlot) => {
    setJump((prev) => jumpToSlot(slot, (prev?.token ?? 0) + 1));
    // На телефоне просмотр бывает ниже экрана или под кнопками: сначала показываем его.
    // jsdom без scrollIntoView: вызов необязательный.
    (viewerRef.current as Partial<HTMLElement> | null)?.scrollIntoView?.({
      block: "start",
      behavior: "smooth",
    });
  };
  const targets = pendingMine(doc).length > 0 ? pendingMine(doc) : doc.mine;
  const panelId = "signing-doc-panel";

  return (
    <section
      className="sgn-docs"
      aria-label={t("docs.title")}
      data-testid="signing-docs"
    >
      {task.docs.length > 1 && (
        <PageTabs
          label={t("docs.tabs")}
          panelId={panelId}
          idPrefix="signing-doc"
          value={doc.doc_id}
          onChange={(id) => {
            setSelected(id);
            setJump(null);
            setPresses(0);
          }}
          tabs={task.docs.map((d) => ({
            id: d.doc_id,
            label: name(d),
            testId: `signing-doc-tab-${d.doc_id}`,
            ...(pendingMine(d).length > 0
              ? { count: pendingMine(d).length, countTone: "accent" as const }
              : {}),
          }))}
        />
      )}
      <div
        id={panelId}
        role={task.docs.length > 1 ? "tabpanel" : undefined}
        className="sgn-docs"
        data-doc={doc.doc_id}
      >
        <div className="sgn-doc-bar">
          {/* С вкладками название уже на вкладке; полоса остаётся для кнопок. */}
          <h2 className={task.docs.length > 1 ? "sr-only" : undefined}>
            {name(doc)}
          </h2>
          {doc.frozen && <Badge variant="subtle">{t("docs.final")}</Badge>}
          {targets.length > 0 && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              data-testid="signing-to-place"
              onClick={() => {
                const slot = targets[presses % targets.length];
                if (slot) goTo(slot);
                setPresses((n) => n + 1);
              }}
            >
              <Crosshair size="0.875rem" aria-hidden />
              {t("docs.toPlace")}
            </Button>
          )}
          <Button asChild size="sm" variant="ghost">
            <a
              href={pdfUrlOf(doc)}
              target="_blank"
              rel="noreferrer"
              data-testid="signing-open-pdf"
            >
              <ExternalLink size="0.875rem" aria-hidden />
              {t("docs.openPdf")}
            </a>
          </Button>
        </div>
        <div className="sgn-viewer" ref={viewerRef}>
          <PdfViewer
            key={doc.doc_id}
            url={pdfUrlOf(doc)}
            // Чужое согласие или фиксация меняют PDF по тому же адресу: перечитываем по событиям.
            refreshKey={`${String(task.route.round)}:${String(task.events.length)}`}
            stamps={myFrames(doc, t("docs.yourSlot"))}
            jump={jump}
            storageKey={`sign:${task.route.project.id}:${doc.doc_id}`}
            // Подписанту важна вся ширина страницы: место подписи часто у правого края.
            initialFit
            ariaLabel={name(doc)}
          />
        </div>
        {doc.mine.length > 0 && (
          <div className="sgn-card">
            <h3>{t("docs.mine")}</h3>
            <ul className="sgn-slots">
              {doc.mine.map((slot) => (
                <li
                  key={slot.slot_id}
                  className="sgn-slot"
                  data-status={slot.status}
                  data-testid={`signing-slot-${slot.slot_id}`}
                >
                  <span className="sgn-slot-label">
                    {pickLocalized(slot.label, i18n.language, slot.slot_id)}
                  </span>
                  <span className="sgn-slot-meta">
                    {t("docs.page", { page: slot.page })} ·{" "}
                    {t(`docs.slot.${slotStatusKey(slot)}`)}
                  </span>
                  <Button
                    type="button"
                    size="xs"
                    variant="ghost"
                    aria-label={t("docs.show")}
                    title={t("docs.show")}
                    onClick={() => {
                      goTo(slot);
                    }}
                  >
                    <Crosshair size="0.875rem" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
            {doc.others.length > 0 && (
              <p className="sgn-others">
                {t("docs.others")}:{" "}
                {doc.others
                  .map(
                    (o) =>
                      `${pickLocalized(o.label, i18n.language, o.slot_id)} (${t(`docs.slot.${o.status}`)})`,
                  )
                  .join(", ")}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
};
