"""cleanable_bytes / unused_app_image_refs / ours_only — the pure rules that
decide what the UI sees and what "Очистить всё" is allowed to touch.
"""

from __future__ import annotations

from hse_doc_studio.infra.docker.system_manager import (
    ContainerUsage,
    DockerDiskUsage,
    ImageUsage,
    VolumeUsage,
)
from hse_doc_studio.use_cases.system.get_docker_disk_usage import (
    cleanable_bytes,
    ours_only,
    unused_app_image_refs,
)


def _image(**overrides: object) -> ImageUsage:
    defaults: dict[str, object] = {
        "reference": "texlive/texlive:latest",
        "repository": "texlive/texlive",
        "tag": "latest",
        "id": "sha256:abc",
        "size_bytes": 100,
        "created": "1 day ago",
        "containers": 0,
        "category": "compile",
        "dangling": False,
        "protected": False,
    }
    defaults.update(overrides)
    return ImageUsage(**defaults)  # type: ignore[arg-type]


def _container(**overrides: object) -> ContainerUsage:
    defaults: dict[str, object] = {
        "name": "hse-languagetool",
        "image": "erikvl87/languagetool:latest",
        "state": "exited",
        "status": "Exited (0) 3 days ago",
        "size_bytes": 100,
        "managed": True,
    }
    defaults.update(overrides)
    return ContainerUsage(**defaults)  # type: ignore[arg-type]


def test__cleanable_bytes__unavailable_docker_is_zero() -> None:
    assert cleanable_bytes(DockerDiskUsage(available=False)) == 0


def test__cleanable_bytes__sums_cache_plus_unprotected_app_images_plus_stopped_managed_containers() -> None:
    usage = DockerDiskUsage(
        available=True,
        images=[
            _image(size_bytes=1_000, protected=False, category="compile"),
            _image(size_bytes=2_000, protected=True, category="compile"),
            # "other" category images are never counted, even if unprotected —
            # they belong to the user's other projects, not to us.
            _image(size_bytes=5_000, protected=False, category="other"),
        ],
        containers=[
            _container(size_bytes=300, managed=True, state="exited"),
            _container(size_bytes=400, managed=True, state="running"),
            _container(size_bytes=500, managed=False, state="exited"),
        ],
        build_cache_reclaimable_bytes=10_000,
    )
    # cache 10_000 + unprotected compile image 1_000 + one stopped managed
    # container 300 — the running one and the foreign one are excluded.
    assert cleanable_bytes(usage) == 11_300


def test__ours_only__drops_foreign_entities_and_recomputes_totals() -> None:
    usage = DockerDiskUsage(
        available=True,
        images=[
            _image(reference="texlive/texlive:latest", size_bytes=1_000, category="compile"),
            _image(reference="sha256:junk", size_bytes=300, category="dangling", dangling=True),
            _image(reference="postgres:17-alpine", size_bytes=9_000, category="other"),
        ],
        containers=[
            _container(name="hse-languagetool", size_bytes=100, managed=True),
            _container(name="user-postgres", size_bytes=5_000, managed=False),
        ],
        volumes=[
            VolumeUsage(name="hse-tex-cache", size_bytes=40, links=1, managed=True),
            VolumeUsage(name="random-volume", size_bytes=7_000, links=1, managed=False),
        ],
        images_total_bytes=999_999,
        containers_total_bytes=999_999,
        volumes_total_bytes=999_999,
        build_cache_bytes=2_000,
        build_cache_reclaimable_bytes=2_000,
        build_cache_count=3,
    )

    ours = ours_only(usage)

    # Foreign image/container/volume never reach the API response…
    assert [i.reference for i in ours.images] == ["texlive/texlive:latest", "sha256:junk"]
    assert [c.name for c in ours.containers] == ["hse-languagetool"]
    assert [v.name for v in ours.volumes] == ["hse-tex-cache"]
    # …and the totals are recomputed over what's left, not docker-wide.
    assert ours.images_total_bytes == 1_300
    assert ours.containers_total_bytes == 100
    assert ours.volumes_total_bytes == 40
    assert ours.build_cache_bytes == 2_000


def test__unused_app_image_refs__excludes_protected_dangling_and_other() -> None:
    usage = DockerDiskUsage(
        available=True,
        images=[
            _image(reference="a", protected=False, category="compile", dangling=False),
            _image(reference="b", protected=True, category="compile", dangling=False),
            _image(reference="c", protected=False, category="other", dangling=False),
            _image(reference="d", protected=False, category="dangling", dangling=True),
        ],
    )
    assert unused_app_image_refs(usage) == ["a"]
