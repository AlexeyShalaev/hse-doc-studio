from __future__ import annotations

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.git_sync.protocols import ILocalAuthorProfile
from hse_doc_studio.core.vcs.author import normalize_email, normalize_name
from hse_doc_studio.core.vcs.entities import VcsAuthor
from hse_doc_studio.core.vcs.errors import ProfileValidationError


class ActorCommitAuthorProvider:
    """Подпись коммита: актор запроса, затем профиль этой машины, затем служебная.

    Актор с именем или e-mail, которые git не примет, подписывается как `fallback`, поэтому
    коммит не падает. Локальный актор и отсутствие запроса (восстановление при старте)
    берут профиль, а без него `fallback`.
    """

    def __init__(self, fallback: VcsAuthor, local_profile: ILocalAuthorProfile | None = None) -> None:
        self._fallback = fallback
        self._local_profile = local_profile

    def author(self) -> VcsAuthor:
        actor = current_actor()
        if actor is not None and actor.kind is not ActorKind.local:
            try:
                return VcsAuthor(normalize_name(actor.name), normalize_email(actor.email, require_domain_dot=False))
            except ProfileValidationError:
                return self._fallback
        return self._profile_author() or self._fallback

    def _profile_author(self) -> VcsAuthor | None:
        if self._local_profile is None:
            return None
        profile = self._local_profile.get()
        return None if profile is None else VcsAuthor(profile.name, profile.email)
