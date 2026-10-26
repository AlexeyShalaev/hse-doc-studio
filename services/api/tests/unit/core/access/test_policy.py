import pytest
from hse_doc_studio.core.access.actions import GUEST_DENIED, ROLE_ACTIONS, Action
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.paths import (
    classify_path,
    normalize_path,
    path_in_author_scope,
    scope_path_of_instance_id,
)
from hse_doc_studio.core.access.policy import Decision, can, decide

USER = Actor.user("u1", "Иван", "ivan@example.com")
GUEST = Actor.guest("l1", "Гость")


def _acl(grant: Grant, *, actor: Actor = USER, team: bool = False, shared_enabled: bool = True) -> ProjectAcl:
    return ProjectAcl(
        project_id="p1", owner_id="owner", team=team, shared_enabled=shared_enabled, grants={actor.key or "": grant}
    )


@pytest.mark.parametrize("action", list(Action))
def test__can__local_actor__allows_every_action(action: Action) -> None:
    acl = _acl(Grant(Role.reader))

    assert can(Actor.local(), action)
    assert can(Actor.local(), action, acl, "../etc/passwd")
    assert decide(Actor.local(), action, None) is Decision.allow


def test__decide__no_acl_or_no_grant__not_found() -> None:
    acl = _acl(Grant(Role.owner))

    assert decide(USER, Action.PROJECT_VIEW, None) is Decision.not_found
    assert decide(Actor.user("stranger"), Action.PROJECT_VIEW, acl) is Decision.not_found
    assert decide(Actor.guest("other"), Action.PROJECT_VIEW, acl) is Decision.not_found


def test__decide__insufficient_role__forbidden() -> None:
    acl = _acl(Grant(Role.reader))

    assert decide(USER, Action.FILES_WRITE, acl, "main.tex") is Decision.forbidden
    assert decide(USER, Action.PROJECT_VIEW, acl) is Decision.allow


_MATRIX = {
    Role.reader: {Action.PROJECT_VIEW, Action.OUTPUT_READ},
    Role.reviewer: {Action.PROJECT_VIEW, Action.OUTPUT_READ, Action.SOURCES_READ, Action.COMMENT},
    Role.editor: {
        Action.PROJECT_VIEW,
        Action.OUTPUT_READ,
        Action.SOURCES_READ,
        Action.COMMENT,
        Action.FILES_WRITE,
        Action.BUILD_RUN,
        Action.AGENT_USE,
        Action.HISTORY_WRITE,
        Action.SUBMISSION_READ,
        Action.SUBMISSION_CREATE,
    },
    Role.owner: set(Action) - {Action.FILES_READ},
}


@pytest.mark.parametrize("role", list(Role))
def test__role_matrix__matches_design_7_1(role: Role) -> None:
    acl = _acl(Grant(role, persona_slug="ivanov", can_share=True, can_edit_all=True))
    # SIGN проверяется отдельно: для него нужен слот с владельцем
    expected = _MATRIX[role] | ({Action.SHARE} if role in (Role.editor, Role.owner) else set())
    expected |= {Action.SIGN} if role is not Role.reader else set()

    allowed = {a for a in Action if a is not Action.FILES_READ and can(USER, a, acl, _path_for(a))}

    assert allowed == expected
    assert allowed <= ROLE_ACTIONS[role] | {Action.SOURCES_READ}


def _path_for(action: Action) -> str | None:
    return "doc--ivanov" if action is Action.SIGN else "main.tex"


@pytest.mark.parametrize("action", sorted(GUEST_DENIED))
def test__guest__denied_agent_share_sign_submission_project_history(action: Action) -> None:
    acl = _acl(Grant(Role.editor, persona_slug="ivanov", can_share=True), actor=GUEST)

    assert decide(GUEST, action, acl, "doc--ivanov") is Decision.forbidden


def test__guest__editor_may_edit_build_and_read() -> None:
    acl = _acl(Grant(Role.editor), actor=GUEST)

    assert all(can(GUEST, a, acl, "main.tex") for a in (Action.FILES_WRITE, Action.BUILD_RUN, Action.SOURCES_READ))


def test__files_read__reader_without_show_sources__only_output_paths() -> None:
    acl = _acl(Grant(Role.reader))

    assert can(USER, Action.FILES_READ, acl, "report/main.pdf")
    assert can(USER, Action.FILES_READ, acl, "report/.build/main/main.log")
    assert not can(USER, Action.FILES_READ, acl, "report/main.tex")
    assert not can(USER, Action.FILES_READ, acl, ".hse-studio/signatures/author--ivanov.png")
    assert not can(USER, Action.FILES_READ, acl)
    assert not can(USER, Action.FILES_READ, acl, "../secret.pdf")


def test__files_read__reader_with_show_sources_and_guest_reader__reads_sources() -> None:
    acl = _acl(Grant(Role.reader, show_sources=True))
    guest_acl = _acl(Grant(Role.reader, show_sources=True), actor=GUEST)

    assert can(USER, Action.FILES_READ, acl, "report/main.tex")
    assert can(USER, Action.SOURCES_READ, acl)
    assert can(GUEST, Action.FILES_READ, guest_acl, "report/main.tex")
    assert not can(GUEST, Action.SOURCES_READ, _acl(Grant(Role.reader), actor=GUEST))


def test__files_read__reviewer__reads_sources_without_flag() -> None:
    assert can(USER, Action.FILES_READ, _acl(Grant(Role.reviewer)), "report/main.tex")


def test__team_author__write_own_and_shared_denied_other_author_and_traversal() -> None:
    acl = _acl(Grant(Role.editor, persona_slug="ivanov"), team=True)

    assert can(USER, Action.FILES_WRITE, acl, "ivanov/main.tex")
    assert can(USER, Action.FILES_WRITE, acl, "shared/intro.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "petrov/main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "ivanov/../petrov/main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "shared/../petrov/main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "\\ivanov\\main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "/ivanov/main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "project.json")
    assert not can(USER, Action.FILES_WRITE, acl, "common/x.tex")
    assert not can(USER, Action.FILES_WRITE, acl)


def test__team_author__shared_disabled__shared_denied() -> None:
    acl = _acl(Grant(Role.editor, persona_slug="ivanov"), team=True, shared_enabled=False)

    assert not can(USER, Action.FILES_WRITE, acl, "shared/intro.tex")
    assert can(USER, Action.FILES_WRITE, acl, "ivanov/main.tex")


def test__team_author__unbound_editor__writes_only_shared() -> None:
    acl = _acl(Grant(Role.editor), team=True)

    assert can(USER, Action.FILES_WRITE, acl, "shared/intro.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "ivanov/main.tex")


def test__team_author__owner_and_edit_all__write_anywhere_but_not_traversal() -> None:
    for grant in (Grant(Role.owner), Grant(Role.editor, can_edit_all=True)):
        acl = _acl(grant, team=True)

        assert can(USER, Action.FILES_WRITE, acl, "petrov/main.tex")
        assert can(USER, Action.FILES_WRITE, acl)
        assert not can(USER, Action.FILES_WRITE, acl, "petrov/../../x")


def test__solo_project__editor_writes_any_valid_path() -> None:
    acl = _acl(Grant(Role.editor))

    assert can(USER, Action.FILES_WRITE, acl, "report/main.tex")
    assert not can(USER, Action.FILES_WRITE, acl, "../x")


def test__sign__requires_persona_slug_equal_to_slot_owner() -> None:
    reviewer = _acl(Grant(Role.reviewer, persona_slug="supervisor"))
    author = _acl(Grant(Role.editor, persona_slug="ivanov"), team=True)
    unbound = _acl(Grant(Role.editor), team=True)

    assert can(USER, Action.SIGN, author, "author--ivanov")
    assert not can(USER, Action.SIGN, author, "author--petrov")
    assert not can(USER, Action.SIGN, unbound, "author--ivanov")
    assert can(USER, Action.SIGN, reviewer, "approve--supervisor")
    assert not can(USER, Action.SIGN, reviewer, "approve--ivanov")
    assert decide(USER, Action.SIGN, author, "author--petrov") is Decision.forbidden


def test__sign__slot_without_owner__only_project_owner() -> None:
    assert not can(USER, Action.SIGN, _acl(Grant(Role.editor, persona_slug="ivanov")), "author")
    assert not can(USER, Action.SIGN, _acl(Grant(Role.editor, persona_slug="ivanov")))
    assert can(USER, Action.SIGN, _acl(Grant(Role.owner)), "author")


def test__share__editor_needs_can_share() -> None:
    assert not can(USER, Action.SHARE, _acl(Grant(Role.editor)))
    assert can(USER, Action.SHARE, _acl(Grant(Role.editor, can_share=True)))
    assert can(USER, Action.SHARE, _acl(Grant(Role.owner)))


def test__submission_create__editor_in_team_only_own_package() -> None:
    acl = _acl(Grant(Role.editor, persona_slug="ivanov"), team=True)

    assert can(USER, Action.SUBMISSION_CREATE, acl, "ivanov")
    assert can(USER, Action.SUBMISSION_CREATE, acl)
    assert not can(USER, Action.SUBMISSION_CREATE, acl, "petrov")
    assert not can(USER, Action.SUBMISSION_CREATE, _acl(Grant(Role.editor), team=True))
    assert can(USER, Action.SUBMISSION_CREATE, _acl(Grant(Role.editor)))


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a/b.tex", "a/b.tex"),
        ("./a//b.tex", "a/b.tex"),
        ("a/../b", None),
        ("a\\b", None),
        ("/a", None),
        ("", None),
        (".", None),
        ("a\0b", None),
    ],
)
def test__normalize_path__cases(path: str, expected: str | None) -> None:
    assert normalize_path(path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("main.pdf", "output"),
        ("report/Main.PDF", "output"),
        ("report/.build/main/main.log", "output"),
        (".build/main/main.pdf", "output"),
        (".build/x.png", "source"),
        (".build/main/main.synctex.gz", "source"),
        ("a/.build/main/main.aux", "source"),
        (".build/main/main.fls", "source"),
        ("docs/.build/m/main.bbl", "source"),
        ("report/main.log", "source"),
        ("report/main.tex", "source"),
        ("report/.build", "source"),
        (".hse-studio/signatures/a.png", "source"),
        ("a/../main.pdf", "source"),
        (None, "source"),
    ],
)
def test__classify_path__cases(path: str | None, expected: str) -> None:
    assert classify_path(path) == expected


def test__path_in_author_scope__solo_project_ignores_scope() -> None:
    acl = ProjectAcl(project_id="p")

    assert path_in_author_scope(acl, Grant(Role.editor), "any/file.tex")
    assert path_in_author_scope(acl, Grant(Role.editor), None)


def test__reader_without_sources__cannot_read_build_intermediates_but_reads_pdf_and_log() -> None:
    acl = _acl(Grant(Role.reader, show_sources=False))

    assert can(USER, Action.FILES_READ, acl, ".build/main/main.pdf")
    assert can(USER, Action.FILES_READ, acl, ".build/main/main.log")
    for hidden in (".build/main/main.synctex.gz", "a/.build/main/main.aux", ".build/main/main.fls"):
        assert not can(USER, Action.FILES_READ, acl, hidden)


def test__scope_path_of_instance_id__author_slug_or_none() -> None:
    assert scope_path_of_instance_id("vkr--alex") == "alex"
    assert scope_path_of_instance_id("sig--alex") == "alex"
    assert scope_path_of_instance_id("vkr") is None


def test__files_write_by_instance_id__editor_writes_own_doc_not_others_nor_ownerless() -> None:
    acl = _acl(Grant(Role.editor, persona_slug="alex"), team=True)

    assert can(USER, Action.FILES_WRITE, acl, scope_path_of_instance_id("vkr--alex"))
    assert not can(USER, Action.FILES_WRITE, acl, scope_path_of_instance_id("vkr--boris"))
    assert not can(USER, Action.FILES_WRITE, acl, scope_path_of_instance_id("vkr"))
