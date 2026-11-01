# Use Case Layer Standards

> Note: this file's `uow.transaction()` / `tx.<repo>` examples come from a template service. In this repo repositories are APP-scope and injected directly; `IUnitOfWork.begin()` only opens an ambient transaction boundary (see `backend-repositories.md` and `docs/design/persistence-server.md`). Where this file disagrees, those win.

Use cases orchestrate business logic and MUST follow these patterns.

## Core Principles

1. **Use cases MUST accept `AsyncUnitOfWork`, NEVER `AsyncSession`**
2. **Use cases MUST NOT import from `infra/` (except for DI registration)**
3. **Use cases MUST work with domain entities and protocols**
4. **Use cases return DTOs or domain entities**

## ✅ Correct Use Case Pattern

```python
# use_cases/users/create_user.py
from uuid import UUID
from core.uow import AsyncUnitOfWork
from core.users.entities import User

class CreateUserUseCase:
    """Create a new user."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, email: str, name: str) -> User:
        """Create user and return domain entity."""
        async with self._uow.transaction() as tx:
            # All DB operations within transaction
            existing_user = await tx.users.get_by_email(email)
            if existing_user:
                raise UserAlreadyExistsError(email)

            user = await tx.users.create(email=email, name=name)

            # Outbox events in same transaction
            await tx.outbox.create(
                UserCreatedEvent(user_id=user.id, email=email)
            )

        return user
```

## ✅ Use Case with Multiple Repositories

```python
class LinkSocialAccountUseCase:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str
    ) -> SocialAccount:
        async with self._uow.transaction() as tx:
            # Access multiple repositories via tx
            user = await tx.users.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(user_id)

            existing_account = await tx.social_accounts.get_by_provider_user_id(
                provider=provider,
                provider_user_id=provider_user_id
            )
            if existing_account:
                raise AccountAlreadyLinkedError()

            account = await tx.social_accounts.create(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
            )

            await tx.outbox.create(
                SocialAccountLinkedEvent(
                    user_id=user_id,
                    account_id=account.id
                )
            )

        return account
```

## ✅ Use Case with Domain Service

```python
from core.users.services import UserDomainService

class UpdateUserProfileUseCase:
    def __init__(
        self,
        uow: AsyncUnitOfWork,
        domain_service: UserDomainService,
    ) -> None:
        self._uow = uow
        self._domain_service = domain_service

    async def execute(self, user_id: UUID, name: str) -> User:
        async with self._uow.transaction() as tx:
            user = await tx.users.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(user_id)

            # Domain logic in domain service
            updated_user = self._domain_service.update_profile(user, name)

            await tx.users.update(updated_user)

        return updated_user
```

## ✅ Read-Only Use Case

```python
class ListUserAccountsUseCase:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, user_id: UUID) -> list[SocialAccount]:
        async with self._uow.transaction() as tx:
            accounts = await tx.social_accounts.list_by_user(user_id)
        return accounts
```

## ❌ Incorrect Patterns

### ❌ NEVER accept AsyncSession
```python
# ❌ WRONG
class CreateUserUseCase:
    def __init__(self, session: AsyncSession) -> None:  # ❌ WRONG
        self._session = session
```

### ❌ NEVER instantiate repositories directly
```python
# ❌ WRONG
class CreateUserUseCase:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow
        self._user_repo = SqlUserRepository(...)  # ❌ WRONG
```

### ❌ NEVER call session.commit() manually
```python
# ❌ WRONG
async def execute(self, email: str) -> User:
    async with self._uow.transaction() as tx:
        user = await tx.users.create(email=email)
        await tx.session.commit()  # ❌ WRONG - UoW handles this
```

### ❌ NEVER import from infra in use cases
```python
# ❌ WRONG
from infra.db.repositories.user import SqlUserRepository  # ❌ WRONG
from infra.clients.google import GoogleOAuthClient  # ❌ WRONG
```

### ❌ NEVER work with ORM models
```python
# ❌ WRONG
async def execute(self, email: str) -> UserDB:  # ❌ Returns ORM
    async with self._uow.transaction() as tx:
        user_db = UserDB(email=email)  # ❌ ORM in use case
        tx.session.add(user_db)  # ❌ Direct session access
```

## Use Case Composition

Use cases can compose other use cases:

```python
class LinkSocialAccountUseCase:
    def __init__(
        self,
        uow: AsyncUnitOfWork,
        oauth_callback_use_case: HandleOAuthCallbackUseCase,
    ) -> None:
        self._uow = uow
        self._oauth_callback_use_case = oauth_callback_use_case

    async def execute(self, user_id: UUID, code: str) -> SocialAccount:
        # Reuse existing use case
        account = await self._oauth_callback_use_case.execute(
            user_id=user_id,
            code=code,
        )
        return account
```

## DI Registration

Use cases are registered in `infra/di/providers/use_cases.py`:

```python
from dishka import Provider, Scope, provide
from core.uow import AsyncUnitOfWork
from use_cases.users.create_user import CreateUserUseCase

class UseCaseProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def get_create_user_use_case(
        self,
        uow: AsyncUnitOfWork
    ) -> CreateUserUseCase:
        return CreateUserUseCase(uow)
```

## Heavy Work Is a Job Kind

Compilation, office conversion, detached-signature verification and submission packing run through the job dispatcher (`IJobDispatcher` from `core/jobs/protocols.py`). A use case MUST NOT import `infra/` to do such work or call a converter, keyring or archiver directly.

To add new heavy work:

1. Add a `JobKind` and a frozen `payload` and `result` (plain data that survives the JSON codec: no paths from the host that the runner cannot see, no secrets) in `core/jobs/`.
2. Register one `JobKindSpec` in `core/jobs/registry.py` with its `JobKindPolicy` (awaitable, detachable, idempotent, embedded concurrency).
3. Write a handler (`IJobHandler`) in `infra/jobs/` and register it in the handler registry. The handler may use infra and ports; the registry tests fail if a kind has no spec.
4. In the use case build the payload and call the dispatcher in the mode the policy allows: `run` (await the result) or `submit_detached` (the HTTP answer does not wait); `submit` is for compile only. Map a failed result to the user-facing error inside the use case, from codes, so texts stay localised there.

Stay in-api behind ports (not jobs yet): signing, PAdES export, freeze stamping, AIA chain download, ONLYOFFICE session and callback configuration, and the Git sync family: probe, connect, fetch, sync, clone, bundle import and export. The sync family carries credentials and runs network git as asyncio subprocesses, which the job payload codec (plain data, no secrets, no host paths) cannot express. It is tracked by `IGitOperationRegistry` instead: one operation per project folder, `is_busy(folder)` is consulted by move and delete of a project, and the long steps are cancellable tasks. Do not add `infra` imports to the allowlist for new work: `tests/unit/architecture/infra_allowlist.txt` only shrinks.

## Summary Checklist

When creating use cases:
- [ ] Accept `AsyncUnitOfWork` in `__init__`, NOT `AsyncSession`
- [ ] Access repositories via `async with self._uow.transaction() as tx:`
- [ ] Return domain entities or DTOs, NOT ORM models
- [ ] Do NOT import from `infra/` (repositories, ORM, clients)
- [ ] Heavy work goes through a job kind and `IJobDispatcher`, not a direct infra call
- [ ] Do NOT call `session.commit()` manually
- [ ] Register in `infra/di/providers/use_cases.py`
- [ ] All database operations within `async with uow.transaction()` block
