import { act, renderHook } from "@testing-library/react";
import { installViewport } from "./testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  PHONE_QUERY,
  TABLET_QUERY,
  useIsPhoneWidth,
  useIsTabletWidth,
  useMediaQuery,
  useViewportClass,
} from ".";

describe("viewport hooks", () => {
  let viewport: ReturnType<typeof installViewport>;
  afterEach(() => {
    viewport.restore();
  });

  describe("at 360 px", () => {
    beforeEach(() => {
      viewport = installViewport(360);
    });

    it("answers right on the first render, with no corrective effect pass", () => {
      const renders: boolean[] = [];
      renderHook(() => {
        const value = useIsPhoneWidth();
        renders.push(value);
        return value;
      });
      expect(renders).toEqual([true]);
    });

    it("tells a phone from a tablet and a desktop", () => {
      expect(renderHook(() => useViewportClass()).result.current).toBe("phone");
      expect(renderHook(() => useIsTabletWidth()).result.current).toBe(false);
    });
  });

  it("treats 767.98 px as a phone and 768 px as a tablet", () => {
    viewport = installViewport(767);
    expect(renderHook(() => useViewportClass()).result.current).toBe("phone");
    viewport.restore();
    viewport = installViewport(768);
    expect(renderHook(() => useViewportClass()).result.current).toBe("tablet");
  });

  it("sees 820x1180 as a tablet and 1024 as a desktop", () => {
    viewport = installViewport(820);
    expect(renderHook(() => useViewportClass()).result.current).toBe("tablet");
    viewport.restore();
    viewport = installViewport(1024);
    expect(renderHook(() => useViewportClass()).result.current).toBe("desktop");
  });

  it("follows the window while it is resized and unsubscribes on unmount", () => {
    viewport = installViewport(1360);
    const { result, unmount } = renderHook(() => useViewportClass());
    expect(result.current).toBe("desktop");
    act(() => {
      viewport.resize(390);
    });
    expect(result.current).toBe("phone");
    act(() => {
      viewport.resize(820);
    });
    expect(result.current).toBe("tablet");
    unmount();
    expect(viewport.listenerCount()).toBe(0);
  });

  it("answers false when matchMedia is missing", () => {
    viewport = installViewport(360);
    // @ts-expect-error окружение без matchMedia
    window.matchMedia = undefined;
    expect(renderHook(() => useMediaQuery(PHONE_QUERY)).result.current).toBe(
      false,
    );
  });

  it("keeps the phone and tablet queries from overlapping", () => {
    viewport = installViewport(767.5);
    expect(renderHook(() => useMediaQuery(PHONE_QUERY)).result.current).toBe(
      true,
    );
    expect(renderHook(() => useMediaQuery(TABLET_QUERY)).result.current).toBe(
      false,
    );
  });
});
