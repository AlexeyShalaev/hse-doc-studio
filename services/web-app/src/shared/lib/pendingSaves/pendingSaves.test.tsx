import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { flushPendingSaves, registerPendingSave } from "./pendingSaves";
import { usePendingSave } from "./usePendingSave";

describe("pendingSaves", () => {
  it("flushes with nothing registered", async () => {
    expect(await flushPendingSaves()).toEqual({ total: 0, failed: 0 });
  });

  it("runs every callback and waits for the async ones", async () => {
    const order: string[] = [];
    const offA = registerPendingSave(async () => {
      await new Promise((r) => setTimeout(r, 20));
      order.push("a");
    });
    const offB = registerPendingSave(() => {
      order.push("b");
    });
    const result = await flushPendingSaves();
    expect(order.sort()).toEqual(["a", "b"]);
    expect(result).toEqual({ total: 2, failed: 0 });
    offA();
    offB();
  });

  it("counts failures without stopping the others", async () => {
    const ok = vi.fn();
    const offBad = registerPendingSave(() => {
      throw new Error("boom");
    });
    const offRejected = registerPendingSave(() =>
      Promise.reject(new Error("x")),
    );
    const offOk = registerPendingSave(ok);
    const result = await flushPendingSaves();
    expect(ok).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ total: 3, failed: 2 });
    offBad();
    offRejected();
    offOk();
  });

  it("stops calling a callback once it is unregistered", async () => {
    const flush = vi.fn();
    const off = registerPendingSave(flush);
    off();
    await flushPendingSaves();
    expect(flush).not.toHaveBeenCalled();
  });

  it("registers a hook for the lifetime of the component and uses its latest closure", async () => {
    const seen: number[] = [];
    const Probe = ({ value }: { value: number }) => {
      usePendingSave(() => {
        seen.push(value);
      });
      return null;
    };
    const { rerender, unmount } = render(<Probe value={1} />);
    rerender(<Probe value={2} />);
    expect((await flushPendingSaves()).total).toBe(1);
    expect(seen).toEqual([2]);
    unmount();
    expect((await flushPendingSaves()).total).toBe(0);
  });
});
