from __future__ import annotations

from unittest.mock import MagicMock, patch

from hse_doc_studio.infra.project_init.materializer import TemplateMaterializer


def test__regenerate_dynamic_includes__delegates_with_template_repo() -> None:
    repo, project, version = MagicMock(), MagicMock(), MagicMock()

    with patch("hse_doc_studio.infra.project_init.materializer.regenerate_dynamic_includes") as regenerate:
        assert TemplateMaterializer(repo).regenerate_dynamic_includes(project, version) is None

    regenerate.assert_called_once_with(project, version, repo)


def test__instantiate_nda__delegates_and_keeps_returned_paths() -> None:
    repo, project, version = MagicMock(), MagicMock(), MagicMock()

    with patch("hse_doc_studio.infra.project_init.materializer.instantiate_nda", return_value=["nda/a.tex"]) as nda:
        assert TemplateMaterializer(repo).instantiate_nda(project, version) == ["nda/a.tex"]

    nda.assert_called_once_with(project, version, repo)
