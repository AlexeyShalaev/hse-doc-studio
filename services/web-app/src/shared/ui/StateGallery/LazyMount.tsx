import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * Собирает содержимое, когда оно подходит к экрану. В галерее больше сотни
 * записей, и часть шагов сама ставит фокус на поле: без отложенной сборки
 * страница при открытии прыгала бы к последнему из них.
 */
export const LazyMount = ({
  children,
  minHeight = 240,
}: {
  children: ReactNode;
  minHeight?: number;
}) => {
  const ref = useRef<HTMLDivElement>(null);
  // Прокрутка страницы до сборки: поле с автофокусом сдвинуло бы её к себе.
  const savedScroll = useRef<number | null>(null);
  // Без IntersectionObserver (тесты, старый браузер) собираем сразу.
  const [isVisible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );

  useEffect(() => {
    const element = ref.current;
    if (isVisible || !element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          savedScroll.current =
            element.closest<HTMLElement>("[data-gallery-scroll]")?.scrollTop ??
            null;
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "700px 0px" },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [isVisible]);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!isVisible || !element || savedScroll.current === null) return;
    const scroller = element.closest<HTMLElement>("[data-gallery-scroll]");
    if (scroller) scroller.scrollTop = savedScroll.current;
    // Фокус остаётся у человека, а не у поля, которое собралось ниже экрана.
    if (
      document.activeElement instanceof HTMLElement &&
      element.contains(document.activeElement)
    ) {
      document.activeElement.blur();
    }
    savedScroll.current = null;
  }, [isVisible]);

  return (
    <div ref={ref} style={isVisible ? undefined : { minHeight }}>
      {isVisible ? children : null}
    </div>
  );
};
