import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import type { GalleryEntry } from "@shared/lib/stateGallery";
import { LazyMount } from "./LazyMount";

export type GalleryDemo = {
  /** Ставит демо-мир в сценарий: состояние проекта, доступы, автор версий. */
  activate: (scenarioId: string) => void;
};

const makeClient = (entry: GalleryEntry): QueryClient => {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // Записи без сервера не должны сами ходить за данными.
        ...(entry.scenario ? {} : { staleTime: Infinity }),
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
  entry.seed?.(client);
  return client;
};

const EntryBody = ({ entry }: { entry: GalleryEntry }) => {
  const [client] = useState(() => makeClient(entry));
  return (
    <QueryClientProvider client={client}>{entry.render()}</QueryClientProvider>
  );
};

const frameStyle = (entry: GalleryEntry): React.CSSProperties => {
  switch (entry.frame ?? "plain") {
    case "window":
      return {
        width: entry.width ?? 680,
        maxWidth: "100%",
        padding: 20,
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
        boxShadow: "var(--shadow-elev-pop, 0 8px 28px rgba(0, 0, 0, 0.28))",
      };
    case "page":
      return {
        width: entry.width ?? 820,
        maxWidth: "100%",
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--bg-0)",
        overflow: "hidden",
      };
    case "screen":
      return {
        height: "max(640px, calc(100vh - 150px))",
        display: "flex",
        flexDirection: "column",
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--bg-0)",
        overflow: "hidden",
      };
    case "plain":
      return entry.width ? { maxWidth: entry.width } : {};
  }
};

export type GalleryEntryCardProps = {
  entry: GalleryEntry;
  /** null: демо недоступно, живые записи не открываются. */
  demo: GalleryDemo | null;
  /**
   * Номер запуска, если эта живая запись сейчас открыта (одновременно только
   * одна), иначе null. Новый номер собирает запись заново.
   */
  activeRun: number | null;
  onOpenLive: (entry: GalleryEntry) => void;
  onCloseLive: () => void;
};

export const GalleryEntryCard = ({
  entry,
  demo,
  activeRun,
  onOpenLive,
  onCloseLive,
}: GalleryEntryCardProps) => {
  const isLive = entry.scenario !== undefined;
  const isActive = isLive && activeRun !== null;

  const open = (): void => {
    onOpenLive(entry);
  };

  return (
    <section
      id={`entry-${entry.id}`}
      aria-labelledby={`entry-title-${entry.id}`}
      data-entry={entry.id}
      style={{ scrollMarginTop: 16 }}
    >
      <header
        className="flex items-start"
        style={{ gap: 12, marginBottom: 10 }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <h4
            id={`entry-title-${entry.id}`}
            style={{ margin: 0, fontSize: 14, fontWeight: 600 }}
          >
            {entry.title}
            {isLive && (
              <span
                className="flex-inline items-center dim"
                style={{
                  display: "inline-flex",
                  gap: 4,
                  marginLeft: 10,
                  fontSize: 11,
                  fontWeight: 500,
                }}
              >
                <FlaskConical size={12} aria-hidden="true" />
                живое
              </span>
            )}
          </h4>
          {entry.note && (
            <p
              className="dim"
              style={{ margin: "3px 0 0", fontSize: 12.5, lineHeight: 1.5 }}
            >
              {entry.note}
            </p>
          )}
        </div>
        <code
          className="mono dim"
          style={{ fontSize: 11, whiteSpace: "nowrap", paddingTop: 2 }}
        >
          {entry.id}
        </code>
      </header>

      {isLive && !isActive && (
        <div
          className="flex items-center"
          style={{
            gap: 12,
            padding: "14px 16px",
            borderRadius: 10,
            border: "1px dashed var(--border)",
            background: "var(--bg-1)",
          }}
        >
          <button
            type="button"
            className="btn primary"
            onClick={open}
            disabled={!demo}
          >
            Открыть
          </button>
          <span className="dim" style={{ fontSize: 12 }}>
            {demo
              ? "Работает на демо-данных в памяти вкладки; сценарий выберется сам."
              : "Демо-режим недоступен в этой сборке."}
          </span>
        </div>
      )}

      {!isLive && (
        <LazyMount>
          <div style={frameStyle(entry)}>
            <EntryBody entry={entry} />
          </div>
        </LazyMount>
      )}

      {isActive && (
        <div style={frameStyle(entry)}>
          <EntryBody key={activeRun} entry={entry} />
        </div>
      )}

      {isActive && (
        <div style={{ marginTop: 8 }} className="flex items-center">
          <button type="button" className="btn sm" onClick={open}>
            Начать заново
          </button>
          <button
            type="button"
            className="btn sm"
            style={{ marginLeft: 8 }}
            onClick={onCloseLive}
          >
            Закрыть
          </button>
        </div>
      )}
    </section>
  );
};
