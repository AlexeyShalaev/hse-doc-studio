// Только для тестов: управляемый matchMedia, у которого ширина окна задаётся числом.
type Listener = () => void;

// Управляемый matchMedia: окно задаёт ширину, запросы считаются по ней.
export const installViewport = (initialWidth: number) => {
  let width = initialWidth;
  const listeners = new Map<string, Set<Listener>>();
  const matches = (query: string): boolean => {
    const min = /min-width:\s*([\d.]+)px/.exec(query);
    const max = /max-width:\s*([\d.]+)px/.exec(query);
    return (
      (min === null || width >= Number(min[1])) &&
      (max === null || width <= Number(max[1]))
    );
  };
  // eslint-disable-next-line @typescript-eslint/unbound-method
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    get matches() {
      return matches(query);
    },
    media: query,
    addEventListener: (_: string, cb: Listener) => {
      const set = listeners.get(query) ?? new Set<Listener>();
      set.add(cb);
      listeners.set(query, set);
    },
    removeEventListener: (_: string, cb: Listener) => {
      listeners.get(query)?.delete(cb);
    },
  })) as unknown as typeof window.matchMedia;
  return {
    resize: (next: number) => {
      width = next;
      listeners.forEach((set) => {
        set.forEach((cb) => {
          cb();
        });
      });
    },
    listenerCount: () =>
      [...listeners.values()].reduce((sum, set) => sum + set.size, 0),
    restore: () => {
      window.matchMedia = original;
    },
  };
};
