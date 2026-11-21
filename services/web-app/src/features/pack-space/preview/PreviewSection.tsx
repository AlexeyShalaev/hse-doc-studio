import PreviewPanel from "./PreviewPanel";

/**
 * Предпросмотр внутри «Подробностей» «Результата» (pack-studio-ux.md, 5.4 пункт 4): выбранный
 * документ, без списка замечаний (тексты правят в «Содержимом»). Открывается параметром `preview=1`.
 */
const PreviewSection = ({ docId, name }: { docId: string; name: string }) => (
  <PreviewPanel key={docId} docId={docId} docName={name} />
);

export default PreviewSection;
