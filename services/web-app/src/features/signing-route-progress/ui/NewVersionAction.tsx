import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import {
  SIGNING_TEXT_MAX,
  signingRouteApi,
  signingRouteKeys,
  useSendSigningRoute,
  type RouteParticipant,
} from "@entities/signing-route";
import { endSentence, pickLocalized, toast } from "@shared/lib";
import { Modal, Spinner, Textarea } from "@shared/ui";
import { newVersionSummary, type NewVersionSummary } from "../lib/routeVersion";
import { useWaitText } from "../lib/useWaitText";
import { useErrorText } from "../model/useErrorText";

export type NewVersionActionProps = {
  projectId: string;
  routeId: string;
  /** Экран маршрута: туда ведём, если отправке что-то мешает. */
  editorPath: string;
  meId: string | null;
  /** Главная кнопка карточки или плашки. */
  primary?: boolean;
  size?: "sm" | "xs";
  disabled?: boolean;
};

type Ready = {
  summary: NewVersionSummary;
  expected: Record<string, string>;
};

/**
 * «Отправить новую версию» (docs/design/signing-route.md, 12.2, 12.6): кнопка спрашивает
 * предпросмотр и показывает подтверждение со следствиями: какие документы изменились, кто
 * согласует заново, что останется как есть. Поле «Что изменилось» необязательное, оно уходит
 * подписантам вместе с запросом. Кнопка есть и на карточке «Подписание», и в плашке редактора.
 */
export const NewVersionAction = ({
  projectId,
  routeId,
  editorPath,
  meId,
  primary = false,
  size = "sm",
  disabled = false,
}: NewVersionActionProps) => {
  const { t, i18n } = useTranslation("signingProgress");
  const navigate = useNavigate();
  const client = useQueryClient();
  const errorText = useErrorText();
  const waitText = useWaitText();
  const send = useSendSigningRoute(projectId, routeId);
  const [isLoading, setIsLoading] = useState(false);
  const [ready, setReady] = useState<Ready | null>(null);
  const [note, setNote] = useState("");

  const docName = (doc: { doc_id: string; name: Record<string, string> }) =>
    pickLocalized(doc.name, i18n.language, doc.doc_id);

  const open = async () => {
    setIsLoading(true);
    try {
      const [route, preview] = await Promise.all([
        client.fetchQuery({
          queryKey: signingRouteKeys.route(projectId, routeId),
          queryFn: ({ signal }) =>
            signingRouteApi.get(projectId, routeId, signal),
          staleTime: 5_000,
        }),
        client.fetchQuery({
          queryKey: signingRouteKeys.preview(projectId, routeId),
          queryFn: ({ signal }) =>
            signingRouteApi.preview(projectId, routeId, signal),
          staleTime: 0,
        }),
      ]);
      if (!preview.can_send) {
        // Изменения успели отправить или откатить: карточка перечитает маршрут.
        if (preview.blockers.every((b) => b.code === "nothing_changed")) {
          toast.info(t("error.nothing_changed"));
          await client.invalidateQueries({
            queryKey: signingRouteKeys.project(projectId),
          });
          return;
        }
        toast.error(t("toast.blocked"));
        void navigate(editorPath);
        return;
      }
      setNote("");
      setReady({
        summary: newVersionSummary(route, preview, meId, docName),
        expected: Object.fromEntries(
          preview.docs.map((doc) => [doc.doc_id, doc.token ?? ""]),
        ),
      });
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setIsLoading(false);
    }
  };

  const close = () => {
    if (!send.isPending) setReady(null);
  };

  const submit = async () => {
    if (ready === null) return;
    try {
      await send.mutateAsync({ expected: ready.expected, sign: null, note });
      toast.success(t("newVersion.sent"));
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setReady(null);
    }
  };

  const names = (people: readonly RouteParticipant[]) =>
    people
      .map((person) => waitText.who({ ...person, cardName: person.card_name }))
      .join(", ");
  const summary = ready?.summary ?? null;

  return (
    <>
      <button
        type="button"
        className={`btn ${size}${primary ? " primary" : ""}`}
        data-testid="signing-new-version"
        disabled={disabled || isLoading || send.isPending}
        onClick={() => {
          void open();
        }}
      >
        {isLoading ? (
          <Spinner size="sm" />
        ) : (
          <Send size="0.75rem" aria-hidden="true" />
        )}
        {t("newVersion.action")}
      </button>
      <Modal
        isOpen={summary !== null}
        onClose={close}
        title={t("newVersion.title")}
        width={480}
        footer={
          <>
            <button
              type="button"
              className="btn"
              disabled={send.isPending}
              onClick={close}
            >
              {t("newVersion.keep")}
            </button>
            <button
              type="submit"
              form="signing-new-version-form"
              className="btn primary"
              data-testid="signing-new-version-confirm"
              disabled={send.isPending}
            >
              {send.isPending && <Spinner size="sm" />}
              {t("newVersion.action")}
            </button>
          </>
        }
      >
        {summary !== null && (
          <form
            id="signing-new-version-form"
            className="flex flex-col"
            style={{ gap: "0.75rem" }}
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <ul
              data-testid="signing-new-version-summary"
              className="flex flex-col"
              style={{
                gap: "0.375rem",
                margin: 0,
                paddingLeft: "1.125rem",
                fontSize: "0.8125rem",
                lineHeight: 1.5,
                color: "var(--fg-1)",
              }}
            >
              {summary.changed.length > 0 && (
                <li data-testid="signing-new-version-changed">
                  {endSentence(
                    t("newVersion.changed", {
                      docs: summary.changed.join(", "),
                    }),
                  )}
                </li>
              )}
              {summary.reapprove.length > 0 && (
                <li data-testid="signing-new-version-reapprove">
                  {endSentence(
                    t("newVersion.reapprove", {
                      people: names(summary.reapprove),
                    }),
                  )}
                </li>
              )}
              {summary.kept.length > 0 && (
                <li data-testid="signing-new-version-kept">
                  {t("newVersion.kept", {
                    docs: summary.kept.join(", "),
                    count: summary.kept.length,
                  })}
                </li>
              )}
            </ul>
            <Textarea
              id="signing-new-version-note"
              label={t("newVersion.note")}
              placeholder={t("newVersion.notePlaceholder")}
              value={note}
              maxLength={SIGNING_TEXT_MAX}
              rows={3}
              data-testid="signing-new-version-note"
              hint={t("newVersion.noteHint")}
              onChange={(e) => {
                setNote(e.target.value);
              }}
            />
          </form>
        )}
      </Modal>
    </>
  );
};
