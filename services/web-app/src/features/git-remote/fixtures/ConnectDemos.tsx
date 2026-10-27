import { useState } from "react";
import { useTranslation } from "react-i18next";
import { gitErrorMessage, type GitContents } from "@entities/git-sync";
import type { CheckOutcome } from "../model/probeOutcome";
import type { CloneVerdict } from "../model/cloneVerdict";
import { CheckStep } from "../ui/CheckStep";
import { CloneVerdictCard } from "../ui/clone/CloneVerdictCard";
import { CloneFolderStep } from "../ui/clone/CloneFolderStep";
import { RepositoryStep } from "../ui/RepositoryStep";
import { CONTENTS, makeProbe } from "./connectFixtures";
import {
  noop,
  parse,
  urlOf,
  type FolderSetup,
  type RepoSetup,
} from "./galleryKit";

export const RepositoryDemo = ({ setup }: { setup: RepoSetup }) => {
  const [url, setUrl] = useState(setup.url);
  const [branch, setBranch] = useState(setup.branch ?? "");
  const [ndaAck, setNdaAck] = useState(false);
  return (
    <RepositoryStep
      url={url}
      onUrlChange={setUrl}
      onUrlCommit={noop}
      tokenStripped={setup.tokenStripped ?? false}
      branch={branch}
      onBranchChange={setBranch}
      parsed={parse(url)}
      ndaRequired={setup.ndaRequired ?? false}
      ndaAck={ndaAck}
      onNdaAckChange={setNdaAck}
      contents={{
        data: setup.contentsState ? undefined : (setup.contents ?? CONTENTS),
        isLoading: setup.contentsState === "loading",
        isError: setup.contentsState === "error",
        refetch: noop,
      }}
      sharedFolder={setup.sharedFolder ?? null}
      onAcknowledgeShared={noop}
      isAcknowledging={false}
      onCancel={noop}
      onNext={noop}
    />
  );
};

export const CheckDemo = ({
  outcome,
  probe,
  fixing = false,
  contents = CONTENTS,
}: {
  outcome: CheckOutcome | null;
  probe: ReturnType<typeof makeProbe> | null;
  fixing?: boolean;
  contents?: GitContents;
}) => {
  const [adopt, setAdopt] = useState(false);
  return (
    <CheckStep
      outcome={outcome}
      probe={probe}
      contents={contents}
      fixing={fixing}
      isConnecting={false}
      adoptConfirmed={adopt}
      onAdoptConfirmedChange={setAdopt}
      onBack={noop}
      onCancel={noop}
      onConnect={noop}
      onAdopt={noop}
      onRetry={noop}
      onBackToRepo={noop}
      onBackToAccess={noop}
      onReviewHostKey={noop}
      onPickBranch={noop}
      onCloneInstead={noop}
    />
  );
};

export const VerdictDemo = ({ verdict }: { verdict: CloneVerdict }) => (
  <CloneVerdictCard
    verdict={verdict}
    probe={makeProbe()}
    url={urlOf("https://github.com/hse-team/paper")}
    branch=""
    onPickBranch={noop}
    onChange={noop}
    issueHandlers={{
      onRetry: noop,
      onBackToRepo: noop,
      onBackToAccess: noop,
      onReviewHostKey: noop,
      onPickBranch: noop,
      onClose: noop,
    }}
  />
);

export const FolderDemo = ({ setup }: { setup: FolderSetup }) => {
  const { t } = useTranslation("gitRemote");
  const [name, setName] = useState(setup.name ?? "paper");
  const [folder, setFolder] = useState(
    setup.folder ?? "/Users/ivan/Documents/HSE/paper",
  );
  return (
    <CloneFolderStep
      sourceLabel="github.com/hse-team/paper"
      name={name}
      namePlaceholder="paper"
      onNameChange={setName}
      folder={folder}
      onFolderChange={setFolder}
      onBrowse={noop}
      inspection={setup.inspection}
      folderError={
        setup.folderErrorCode
          ? gitErrorMessage(setup.folderErrorCode, "")
          : null
      }
      startError={setup.startFailed ? t("clone.folder.failed") : null}
      isStarting={setup.isStarting ?? false}
      onBack={noop}
      onStart={noop}
    />
  );
};
