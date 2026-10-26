import type { SyncAnnouncement } from "../model/useSyncAnnouncer";

// Невидимые области для скринридера: вежливая и настойчивая. Текст в них
// появляется только при смене состояния, поэтому каждый опрос не озвучивается.
export const SyncLiveRegion = ({
  announcement,
}: {
  announcement: SyncAnnouncement;
}) => (
  <>
    <div role="status" aria-live="polite" className="sr-only">
      {announcement.polite}
    </div>
    <div role="alert" aria-live="assertive" className="sr-only">
      {announcement.assertive}
    </div>
  </>
);
