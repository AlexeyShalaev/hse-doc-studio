import { useEffect, useMemo, useSyncExternalStore } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { invalidateReview } from "@entities/review";
import { env } from "@shared/config";
import {
  CollabProvider,
  type CollabServerEvent,
  type CollabSnapshot,
} from "./collabProvider";
import { collabUrl } from "./collabUrl";

const IDLE: CollabSnapshot = {
  status: "connecting",
  synced: false,
  everSynced: false,
  canWrite: false,
  refusal: null,
  peers: [],
  problem: null,
};

export type CollabSession = {
  provider: CollabProvider | null;
  snapshot: CollabSnapshot;
  /** Растёт при сбросе эпохи: редактор нужно открыть заново на новом документе. */
  generation: number;
};

export type CollabSessionOptions = {
  projectId: string;
  path: string;
  /** Эпоха комнаты сменилась: набранное здесь нужно сохранить, редактор откроется заново. */
  onReset?: (localText: string) => void;
};

/**
 * Хранилище сессии одного файла. Сокет открывается, когда на хранилище подписывается первый
 * слушатель, и закрывается с уходом последнего: так сессия переживает двойной запуск эффектов в
 * StrictMode и не течёт при размонтировании.
 */
class SessionStore {
  onReset: ((localText: string) => void) | undefined;
  private provider: CollabProvider | null = null;
  private generation = 0;
  private state: CollabSession = {
    provider: null,
    snapshot: IDLE,
    generation: 0,
  };
  private readonly listeners = new Set<() => void>();
  private stops: (() => void)[] = [];

  constructor(
    private readonly projectId: string,
    private readonly path: string,
    private readonly queryClient: QueryClient,
  ) {}

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    if (this.listeners.size === 1) this.open();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.close();
    };
  };

  readonly getSnapshot = (): CollabSession => this.state;

  private publish(): void {
    const provider = this.provider;
    this.state = {
      provider,
      snapshot: provider ? provider.getSnapshot() : IDLE,
      generation: this.generation,
    };
    this.listeners.forEach((listener) => {
      listener();
    });
  }

  private open(): void {
    const created = new CollabProvider({
      url: () => collabUrl(env.VITE_API_BASE_URL, this.projectId, this.path),
    });
    this.provider = created;
    this.stops = [
      created.subscribe(() => {
        this.publish();
      }),
      created.onEvent((event: CollabServerEvent) => {
        if (event.type === "review") {
          void invalidateReview(this.queryClient, this.projectId);
        } else if (event.type === "reset") {
          this.onReset?.(created.text.toJSON());
          this.generation += 1;
          this.close();
          this.open();
        }
      }),
    ];
    this.publish();
  }

  private close(): void {
    this.stops.forEach((stop) => {
      stop();
    });
    this.stops = [];
    this.provider?.destroy();
    this.provider = null;
  }
}

/**
 * Сессия совместной правки одного файла. Провайдер живёт, пока файл открыт; после сброса эпохи
 * создаётся заново, а `generation` подсказывает редактору открыться на новом документе.
 */
export const useCollabSession = ({
  projectId,
  path,
  onReset,
}: CollabSessionOptions): CollabSession => {
  const queryClient = useQueryClient();
  const store = useMemo(
    () => new SessionStore(projectId, path, queryClient),
    [projectId, path, queryClient],
  );
  useEffect(() => {
    store.onReset = onReset;
  }, [store, onReset]);
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
};
