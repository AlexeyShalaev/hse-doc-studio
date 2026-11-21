import { lazy, type ComponentType } from "react";
import type {
  ContentPart,
  ContentPartProps,
  DocSegment,
  DocumentSegmentProps,
} from "./contract";

// Файлы-расширения области (docs/design/pack-studio-ux.md, 12.7): `extend/segment-<сегмент>.tsx`
// и `extend/part-<раздел>.tsx` с `export default` компонентом. Находятся глобом по имени и
// грузятся лениво: срез S8b, S8c или S8d заменяет свой файл целиком и не правит чужие.
const modules = import.meta.glob<{ default: ComponentType }>("./extend/*.tsx");

const extension = <P>(name: string): ComponentType<P> | null => {
  const load = modules[`./extend/${name}.tsx`];
  return load ? (lazy(load) as unknown as ComponentType<P>) : null;
};

// Собираются один раз при загрузке модуля: компонент не создаётся при отрисовке.
export const SEGMENT_COMPONENTS: Record<
  DocSegment,
  ComponentType<DocumentSegmentProps> | null
> = {
  terms: extension("segment-terms"),
  text: extension("segment-text"),
  signatures: extension("segment-signatures"),
};

export const PART_COMPONENTS: Record<
  ContentPart,
  ComponentType<ContentPartProps> | null
> = {
  fields: extension("part-fields"),
  forms: extension("part-forms"),
  deadlines: extension("part-deadlines"),
  signatures: extension("part-signatures"),
  languages: extension("part-languages"),
  rules: extension("part-rules"),
  files: extension("part-files"),
};
