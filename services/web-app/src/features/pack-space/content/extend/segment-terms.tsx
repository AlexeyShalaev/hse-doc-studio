import type { DocumentSegmentProps } from "../contract";
import { FormPane } from "../FormPane";
import { useContentNav } from "../useContentNav";

// «Условия» документа: когда он нужен студенту (виды работы, состав, языки), название, имя
// файла, варианты. Это прежняя форма документа `pack-forms` (S8a, срез свой и не временный:
// форма уже написана под этот сегмент).
const TermsSegment = ({ workspaceId, doc }: DocumentSegmentProps) => {
  const nav = useContentNav();
  return (
    <FormPane
      workspaceId={workspaceId}
      path={doc.manifestPath}
      onOpenFile={nav.toFile}
    />
  );
};

export default TermsSegment;
