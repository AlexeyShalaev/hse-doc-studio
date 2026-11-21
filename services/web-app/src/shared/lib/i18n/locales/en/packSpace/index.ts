// Все JSON области этого языка одним модулем: ключ верхнего уровня это имя файла (область).
const areas = import.meta.glob<Record<string, unknown>>("./*.json", {
  eager: true,
  import: "default",
});

export default Object.fromEntries(
  Object.entries(areas).map(([path, dict]) => [
    path.replace(/^\.\/(.+)\.json$/, "$1"),
    dict,
  ]),
);
