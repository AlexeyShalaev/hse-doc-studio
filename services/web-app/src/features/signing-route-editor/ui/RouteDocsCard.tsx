import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { clsx } from "clsx";
import { useStartCompile } from "@entities/compile";
import type {
  SigningRoute,
  SigningRoutePreview,
} from "@entities/signing-route";
import { pickLocalized } from "@shared/lib";

export type RouteDocsCardProps = {
  projectId: string;
  route: SigningRoute;
  preview: SigningRoutePreview | undefined;
  editable: boolean;
};

/** «Документы точки»: собран ли каждый документ маршрута. Без сборки отправить нельзя. */
export const RouteDocsCard = ({
  projectId,
  route,
  preview,
  editable,
}: RouteDocsCardProps) => (
  <div className="flex flex-col">
    {route.docs.map((doc) => {
      const shown = preview?.docs.find((d) => d.doc_id === doc.doc_id);
      return (
        <DocRow
          key={doc.doc_id}
          projectId={projectId}
          docId={doc.doc_id}
          name={doc.name}
          built={shown?.built ?? null}
          frozen={doc.frozen}
          elsewhere={(preview?.blockers ?? []).some(
            (b) => b.code === "doc_in_other_route" && b.doc_id === doc.doc_id,
          )}
          editable={editable}
        />
      );
    })}
  </div>
);

const DocRow = ({
  projectId,
  docId,
  name,
  built,
  frozen,
  elsewhere,
  editable,
}: {
  projectId: string;
  docId: string;
  name: Record<string, string>;
  /** null: предпросмотр ещё не пришёл. */
  built: boolean | null;
  frozen: boolean;
  elsewhere: boolean;
  editable: boolean;
}) => {
  const { t, i18n } = useTranslation("signingRouteEditor");
  const navigate = useNavigate();
  const { start, isRunning, slot, block } = useStartCompile(projectId, docId);
  const building = slot?.status === "running";
  const tone = elsewhere || built === false ? "warn" : built ? "ok" : "pending";
  const status = building
    ? t("docs.building")
    : elsewhere
      ? t("docs.elsewhere")
      : built === null
        ? ""
        : built
          ? frozen
            ? t("docs.frozen")
            : t("docs.built")
          : t("docs.notBuilt");
  return (
    <div
      className="flex items-center"
      style={{
        gap: "0.625rem",
        padding: "0.5rem 0",
        borderTop: "1px solid var(--border)",
        flexWrap: "wrap",
      }}
      data-testid={`route-doc-${docId}`}
    >
      <span className={clsx("dot", tone)} />
      <span
        className="truncate"
        style={{ flex: 1, minWidth: "8rem", fontSize: "0.8125rem" }}
      >
        {pickLocalized(name, i18n.language, docId)}
      </span>
      <span
        style={{
          fontSize: "0.71875rem",
          color: tone === "warn" ? "var(--c-warn)" : "var(--fg-2)",
        }}
      >
        {status}
      </span>
      {editable && (
        <button
          type="button"
          className={built === false ? "btn xs primary" : "btn xs"}
          disabled={isRunning || block !== null}
          title={block ? t("docs.noRunner") : undefined}
          onClick={start}
        >
          {t("docs.build")}
        </button>
      )}
      <button
        type="button"
        className="btn xs ghost"
        onClick={() => {
          void navigate(
            `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(docId)}`,
          );
        }}
      >
        {t("docs.open")}
      </button>
    </div>
  );
};
