"""Docker-wide disk usage probe + targeted cleanup.

Backs Settings → «Диск»: how many gigabytes the app's Docker footprint takes
(TeX Live, LanguageTool, Gotenberg, ONLYOFFICE, Ollama, build cache…) and the
safe cleanup actions. Everything goes through the shared `docker` CLI helper;
sizes come from `docker system df -v` (human strings parsed into bytes — the
chart doesn't need byte precision, and one call covers images, containers,
volumes and build cache at once).

Safety model: cleanup only ever touches (a) build cache, (b) dangling images,
(c) images in the app's own categories that no container uses and that aren't
the configured/active image of their category, (d) STOPPED containers carrying
`MANAGED_LABEL` — the label the app itself sets (`docker run --label`) on
every auxiliary container it spawns (see cli.py). A container is identified as
ours by that label, never by its name: a `--name` is just a string the user
could coincidentally reuse for something unrelated, whereas the label is proof
we created it. Images and containers from the user's other projects are
returned here (category «other» / managed=False) for the cleanup logic to
reason about, but the usage UC filters them out before the API response — the
UI shows only the app's own footprint, and cleanup never touches them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

from hse_doc_studio.infra.docker.cli import MANAGED_LABEL, run_docker

logger = structlog.get_logger()

_MANAGED_LABEL_RE = re.compile(rf"(?:^|,){re.escape(MANAGED_LABEL)}=true(?:,|$)")


def _is_managed(labels: str) -> bool:
    return bool(_MANAGED_LABEL_RE.search(labels))


_DF_TIMEOUT_S = 90.0
_LIST_TIMEOUT_S = 30.0
_INSPECT_TIMEOUT_S = 10.0
_PRUNE_TIMEOUT_S = 600.0
_REMOVE_TIMEOUT_S = 300.0

# docker prints decimal units ("8.72GB", "12.1MB", "0B", also "17.7GB (51%)").
_SIZE_RE = re.compile(r"([\d.]+)\s*([kKMGT]?i?B)")
_UNITS = {
    "B": 1,
    "kB": 10**3,
    "KB": 10**3,
    "MB": 10**6,
    "GB": 10**9,
    "TB": 10**12,
    "KiB": 2**10,
    "MiB": 2**20,
    "GiB": 2**30,
    "TiB": 2**40,
}
_RECLAIMED_RE = re.compile(r"[Tt]otal reclaimed space:\s*(.+)")

DANGLING_CATEGORY = "dangling"
OTHER_CATEGORY = "other"


def parse_size(text: str | None) -> int:
    """Parse a docker human-readable size ("8.72GB", "12.2MB (virtual …)") into bytes.

    Only the FIRST size token is read, so container sizes like
    "12.2MB (virtual 6.07GB)" yield the writable-layer part. "N/A"/"" → 0.
    """
    if not text:
        return 0
    match = _SIZE_RE.search(text)
    if match is None:
        return 0
    number, unit = match.groups()
    factor = _UNITS.get(unit) or _UNITS.get(unit.upper().replace("IB", "iB"), 1)
    try:
        return int(float(number) * factor)
    except ValueError:
        return 0


@dataclass(frozen=True)
class ImageUsage:
    reference: str
    repository: str
    tag: str
    id: str
    size_bytes: int
    created: str
    containers: int
    category: str
    dangling: bool
    protected: bool


@dataclass(frozen=True)
class ContainerUsage:
    name: str
    image: str
    state: str
    status: str
    size_bytes: int
    managed: bool


@dataclass(frozen=True)
class VolumeUsage:
    name: str
    size_bytes: int
    links: int
    managed: bool


@dataclass(frozen=True)
class DockerDiskUsage:
    available: bool
    images: list[ImageUsage] = field(default_factory=list)
    containers: list[ContainerUsage] = field(default_factory=list)
    volumes: list[VolumeUsage] = field(default_factory=list)
    # Totals from the `docker system df` summary — deduplicated across shared
    # layers, unlike a naive sum of per-image sizes.
    images_total_bytes: int = 0
    containers_total_bytes: int = 0
    volumes_total_bytes: int = 0
    build_cache_bytes: int = 0
    build_cache_reclaimable_bytes: int = 0
    build_cache_count: int = 0

    @property
    def total_bytes(self) -> int:
        return self.images_total_bytes + self.containers_total_bytes + self.volumes_total_bytes + self.build_cache_bytes


@dataclass(frozen=True)
class CleanupResult:
    target: str
    freed_bytes: int
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DockerSystemManager:
    def __init__(
        self,
        category_by_repo: dict[str, str],
        app_repo_prefix: str,
        managed_volume_names: frozenset[str],
    ) -> None:
        self._category_by_repo = dict(category_by_repo)
        self._app_repo_prefix = app_repo_prefix.rstrip("/")
        # Volumes can't carry a docker-run --label (they're created implicitly
        # by the first `-v <name>:...` mount, with no create step of our own to
        # attach one to) and disk cleanup never deletes a volume today, so a
        # name check is enough here — it only feeds the informational "managed"
        # badge in the usage listing, not a delete decision.
        self._managed_volume_names = managed_volume_names

    # ------------------------------------------------------------------ usage

    async def disk_usage(self, protected_refs: frozenset[str]) -> DockerDiskUsage:
        rc, out, err = await run_docker(["system", "df", "-v", "--format", "{{json .}}"], timeout=_DF_TIMEOUT_S)
        if rc != 0:
            logger.info("docker disk usage probe failed", rc=rc, err=err.strip()[:200])
            return DockerDiskUsage(available=False)
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            logger.warning("docker system df -v returned unparsable output")
            return DockerDiskUsage(available=False)

        images = [self._map_image(entry, protected_refs) for entry in data.get("Images") or []]
        containers = [self._map_container(entry) for entry in data.get("Containers") or []]
        volumes = [self._map_volume(entry) for entry in data.get("Volumes") or []]
        summary = await self._summary()
        images_total, _, _ = summary.get("Images", (sum(i.size_bytes for i in images), 0, 0))
        containers_total, _, _ = summary.get("Containers", (sum(c.size_bytes for c in containers), 0, 0))
        volumes_total, _, _ = summary.get("Local Volumes", (sum(v.size_bytes for v in volumes), 0, 0))
        cache_bytes, cache_reclaimable, cache_count = summary.get("Build Cache", (0, 0, 0))
        return DockerDiskUsage(
            available=True,
            images=images,
            containers=containers,
            volumes=volumes,
            images_total_bytes=images_total,
            containers_total_bytes=containers_total,
            volumes_total_bytes=volumes_total,
            build_cache_bytes=cache_bytes,
            build_cache_reclaimable_bytes=cache_reclaimable,
            build_cache_count=cache_count,
        )

    def _classify(self, repository: str) -> str:
        if repository in self._category_by_repo:
            return self._category_by_repo[repository]
        if self._app_repo_prefix and repository.startswith(self._app_repo_prefix):
            return "app"
        return OTHER_CATEGORY

    def _map_image(self, entry: dict[str, object], protected_refs: frozenset[str]) -> ImageUsage:
        repository = str(entry.get("Repository") or "")
        tag = str(entry.get("Tag") or "")
        image_id = str(entry.get("ID") or "")
        dangling = repository in ("", "<none>") or tag in ("", "<none>")
        reference = image_id if dangling else f"{repository}:{tag}"
        try:
            containers = int(str(entry.get("Containers") or "0"))
        except ValueError:
            containers = 0
        category = DANGLING_CATEGORY if dangling else self._classify(repository)
        return ImageUsage(
            reference=reference,
            repository=repository,
            tag=tag,
            id=image_id,
            size_bytes=parse_size(str(entry.get("Size") or "")),
            created=str(entry.get("CreatedSince") or ""),
            containers=containers,
            category=category,
            dangling=dangling,
            protected=(reference in protected_refs or containers > 0),
        )

    def _map_container(self, entry: dict[str, object]) -> ContainerUsage:
        name = str(entry.get("Names") or entry.get("Name") or "")
        status = str(entry.get("Status") or "")
        state = str(entry.get("State") or "")
        if not state:
            state = "running" if status.startswith("Up") else "exited"
        return ContainerUsage(
            name=name,
            image=str(entry.get("Image") or ""),
            state=state,
            status=status,
            size_bytes=parse_size(str(entry.get("Size") or "")),
            managed=_is_managed(str(entry.get("Labels") or "")),
        )

    def _map_volume(self, entry: dict[str, object]) -> VolumeUsage:
        name = str(entry.get("Name") or "")
        try:
            links = int(str(entry.get("Links") or "0"))
        except ValueError:
            links = 0
        return VolumeUsage(
            name=name,
            size_bytes=parse_size(str(entry.get("Size") or "")),
            links=links,
            managed=name in self._managed_volume_names,
        )

    async def _summary(self) -> dict[str, tuple[int, int, int]]:
        """Per-type (size, reclaimable, count) from the non-verbose df summary rows."""
        rc, out, _err = await run_docker(["system", "df", "--format", "{{json .}}"], timeout=_LIST_TIMEOUT_S)
        if rc != 0:
            return {}
        summary: dict[str, tuple[int, int, int]] = {}
        for line in out.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                count = int(str(row.get("TotalCount") or "0"))
            except ValueError:
                count = 0
            summary[str(row.get("Type") or "")] = (
                parse_size(str(row.get("Size") or "")),
                parse_size(str(row.get("Reclaimable") or "")),
                count,
            )
        return summary

    # ---------------------------------------------------------------- cleanup

    async def prune_build_cache(self) -> CleanupResult:
        rc, out, err = await run_docker(["builder", "prune", "-f"], timeout=_PRUNE_TIMEOUT_S)
        if rc != 0:
            return CleanupResult(target="build_cache", freed_bytes=0, errors=[_short_err(err)])
        return CleanupResult(target="build_cache", freed_bytes=_parse_reclaimed(out))

    async def prune_dangling_images(self) -> CleanupResult:
        rc, out, err = await run_docker(["image", "prune", "-f"], timeout=_PRUNE_TIMEOUT_S)
        if rc != 0:
            return CleanupResult(target="dangling_images", freed_bytes=0, errors=[_short_err(err)])
        return CleanupResult(target="dangling_images", freed_bytes=_parse_reclaimed(out))

    async def remove_images(self, references: list[str], target: str = "unused_images") -> CleanupResult:
        freed = 0
        removed: list[str] = []
        errors: list[str] = []
        for reference in references:
            size = await self._image_size(reference)
            # No --force: an image that is still referenced fails loudly instead
            # of being untagged under a running container's feet.
            rc, _out, err = await run_docker(["image", "rm", reference], timeout=_REMOVE_TIMEOUT_S)
            if rc == 0:
                freed += size
                removed.append(reference)
            else:
                errors.append(f"{reference}: {_short_err(err)}")
        return CleanupResult(target=target, freed_bytes=freed, removed=removed, errors=errors)

    async def remove_stopped_managed_container(self, name: str) -> CleanupResult:
        """Remove ONE stopped app-managed container, re-verifying ownership now.

        The label filter runs server-side at DELETE time (not just when the
        plan was built), so docker never even returns a container we didn't
        create — a name collision with something the user runs independently
        can't reach the `rm`. Running containers are refused, not stopped.
        """
        rc, out, err = await run_docker(
            ["ps", "-a", "-s", "--filter", f"label={MANAGED_LABEL}=true", "--format", "{{json .}}"],
            timeout=_LIST_TIMEOUT_S,
        )
        if rc != 0:
            return CleanupResult(target="container", freed_bytes=0, errors=[_short_err(err)])
        for line in out.splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(entry.get("Names") or "") != name:
                continue
            if str(entry.get("State") or "") == "running":
                return CleanupResult(target="container", freed_bytes=0, errors=[f"{name}: контейнер запущен"])
            size = parse_size(str(entry.get("Size") or ""))
            rm_rc, _rm_out, rm_err = await run_docker(["rm", name], timeout=_REMOVE_TIMEOUT_S)
            if rm_rc != 0:
                return CleanupResult(target="container", freed_bytes=0, errors=[f"{name}: {_short_err(rm_err)}"])
            return CleanupResult(target="container", freed_bytes=size, removed=[name])
        # Absent or unlabeled — either way there is nothing of OURS to delete.
        return CleanupResult(target="container", freed_bytes=0, errors=[f"{name}: управляемый контейнер не найден"])

    async def _image_size(self, reference: str) -> int:
        rc, out, _err = await run_docker(
            ["image", "inspect", "--format", "{{.Size}}", reference], timeout=_INSPECT_TIMEOUT_S
        )
        if rc != 0:
            return 0
        try:
            return int(out.strip().splitlines()[0])
        except (ValueError, IndexError):
            return 0


def _parse_reclaimed(out: str) -> int:
    match = _RECLAIMED_RE.search(out)
    return parse_size(match.group(1)) if match else 0


def _short_err(err: str) -> str:
    text = err.strip().splitlines()
    return text[-1][:300] if text else "docker command failed"
