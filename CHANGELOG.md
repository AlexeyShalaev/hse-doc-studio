# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.4.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.3.0...v0.4.0) (2026-11-03)


### Features

* **deploy:** HSE_STUDIO_CONNECT открывает экран подключения к серверу после установки ([92f6e0d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/92f6e0deb1c53e8c80f94e925bd72838a9ba927c))
* **git-remote:** сведения для локальной Студии и проверка сервера перед подключением ([583a5ab](https://github.com/AlexeyShalaev/hse-doc-studio/commit/583a5abe808b34aeb5af79443a955c7e5953966d))
* **helm:** runner.executor=kubernetes с RBAC на свой namespace и NetworkPolicy ([a40fd77](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a40fd7748c0cbe610090b6a756ba072cbc0ca862))
* **identity:** вход по passkey (WebAuthn), ключи в профиле, повторное подтверждение личности и сброс ключей в админке ([41d713e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/41d713e129b123e3ab2f0717ea724bd12c24c530))
* **identity:** регистрация по приглашению сразу с passkey, письма о добавлении и сбросе ключей, число ключей в списке людей ([ba96aa3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ba96aa36ae0269e995b7f4cd3d37dede88732f67))
* **mcp:** MCP-сервер Студии на /mcp (бэкенд) ([38f45e6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/38f45e68aca7071e3f1e8f87fad35febfbf3ef87))
* **mcp:** MCP-сервер Студии на /mcp: каталог тулов, права, PAT с областью mcp, настройки и журнал ([fea9fd0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fea9fd0748ac1af5618925fcf55b82bbc40a4003))
* **mcp:** админка MCP, раздел «ИИ-клиенты (MCP)» в настройках, права токена mcp ([c8416f2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c8416f2ad9754867f1e55c90db1505ad3622b238))
* **mcp:** админка MCP, раздел настроек «ИИ-клиенты (MCP)» и права токена mcp ([c58aa0d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c58aa0d84bb95ed4a40fa08566cb06b74aceef29))
* **mcp:** команда hse-doc-studio mcp — мост stdio к MCP-серверу Студии ([eaa59fc](https://github.com/AlexeyShalaev/hse-doc-studio/commit/eaa59fc00943cbb5e45ff5b13271cfbb6e35d3e5))
* **mcp:** команда hse-doc-studio mcp: мост stdio к /mcp работающей Студии ([13557ce](https://github.com/AlexeyShalaev/hse-doc-studio/commit/13557ceee0a63f25aef582240aab9d0809c60628))
* **onboarding:** «Локальная версия» в итоге онбординга; тест журнала аудита без полуночного флейка ([d3a9959](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d3a99598997f2a0b9a8e994a3832beed55888286))
* **onboarding:** анкета, тур с подсветкой и демо-проект в песочнице, меню «Справка» и «Пройти заново» ([fbdbe02](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fbdbe02f13aafbe83a14f541e77326760484ba17))
* **onboarding:** доступность облачной сборки в итоге онбординга ([8d96266](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8d9626648cad21fd58ef2a6b27dc2861a9c2fc1b))
* **onboarding:** итог честно говорит, доступна ли облачная сборка: GET /build-availability без проекта ([7ab9677](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7ab967734b3a33d700e95c15e282ca5d2c77348f))
* **onboarding:** кнопка «Локальная версия» в итоге без раннеров; закреплено «сейчас» в тесте журнала аудита ([9b20bec](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9b20becfa031dee454de1d26f351061fa473d004))
* **onboarding:** полноценный онбординг: анкета, тур с подсветкой, демо-проект ([ddebd30](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ddebd308a262a279ae536d333f216439e8df82b0))
* **onboarding:** состояние онбординга пользователя в базе и API чтения, обновления и сброса ([877b7ff](https://github.com/AlexeyShalaev/hse-doc-studio/commit/877b7ff567a45691cb2fa638cce3721d04f0b3e3))
* **passkeys:** регистрация по приглашению с passkey, письма о ключах, колонка в таблице людей ([81dca28](https://github.com/AlexeyShalaev/hse-doc-studio/commit/81dca28151a0d44100f29d8af6de2fb54ef9e633))
* **runner:** исполнитель kubernetes, сборка TeX подом на задачу ([01872d8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/01872d8e452de07edb7ca7d3260b59bf5908b31d))
* **runner:** исполнитель kubernetes, сборка TeX подом на задачу ([5c4e26a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5c4e26a14d372cfb4568cf65ff6f3f5d18fdec41))
* **web:** «Собрать локально» в плашке «облачная сборка недоступна» ведёт на «Локальную версию» с проектом ([8bf79a1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8bf79a1709546bfcf9e35a25ad9c91f3d678fafd))
* **web:** «Собрать локально» в плашке недоступной облачной сборки ([823dde3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/823dde39c066fbc5784c2037cac36942b6ad20d9))
* **web:** кнопка и автозаполнение passkey на входе, карточка passkey в аккаунте, политика и сброс ключей в админке ([3f8bb67](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3f8bb674dbd1b94da0502b4d6c146424033c68f4))
* **web:** создание аккаунта с passkey на странице приглашения, колонка passkey в таблице людей ([ee22a1c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ee22a1ccc92c084bf8015ab34fded204d213afb1))
* **web:** экран «Локальная версия» в облаке и «Подключиться к серверу» в локальной Студии ([5b83b8a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5b83b8a59bdae021dac774b288cd4d7b2c06e14e))
* вход по passkey (WebAuthn) ([51fd822](https://github.com/AlexeyShalaev/hse-doc-studio/commit/51fd822d7747e14a18f8dd71512ad12d15573b58))
* локальная версия из облака и подключение к нему ([4b2718a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4b2718ad3cb2cd74eac85050f5765f3b49bcf48e))
* пользовательская справка со скриншотами, роликами и контекстной помощью ([#116](https://github.com/AlexeyShalaev/hse-doc-studio/issues/116)) ([6136b93](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6136b9385b95733a9cb13ee742b5dcd15cfcbe92))
* релиз 0.4.0 — раннеры в Kubernetes, MCP, онбординг, справка, passkeys ([55359d8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/55359d814425a3eb196743b424c8ab5396e7722b))


### Bug Fixes

* **api:** коды no_runners и no_runner_for_tags в каталоге ошибок с локализованным текстом; тест без unbound-method ([6dc6cf9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6dc6cf9dedf774fb1c1f53e8f078e5ae8f58b68a))
* **api:** сборка без раннеров отвечает 409 no_runners/no_runner_for_tags и эндпоинт доступности сборки ([fd229fa](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fd229fa3e40992b6a5f34c08a748a5bb5b57b10b))
* **ci:** имя образа строчными буквами при подписи cosign и в image-digest.json ([3a908e6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3a908e6c4e62eacb9aa4d8e7b12fb333472c95db))
* **ci:** имя образа строчными буквами при подписи cosign и в image-digest.json ([b9329a9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b9329a98cfd3cfeabfa9253229fded50c61a3319))
* **mcp:** подписи событий аудита mcp.call и settings.mcp_update ([fb8a880](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fb8a88055171a4cb4b5c5f22ee1d60d24f4e03ba))
* **mcp:** событие settings.mcp_update в матрице аудита, тест cookie принимает отказ CSRF ([ecee612](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ecee6124fb65e2cf8e7ad815e86b84f95318d780))
* **onboarding:** серверный тест API без extra server не собирается, RootLayout ждёт запрос состояния онбординга ([5986bf9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5986bf90ffab71663ef8d91ae89d142c704f31fd))
* **onboarding:** сохранения прогресса по очереди, чтобы одновременные PATCH не затирали ответы анкеты ([2e85a2e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2e85a2e82956da3ae68645fc9ca20c39716c8329))
* **passkeys:** свой лимит запросов для вызовов passkey и без бесконечных повторов автозаполнения ([ab8770e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ab8770e1c88eb0ef753acb66d9d614326175281e))
* **web:** автозаполнение passkey молчит, если браузер его не умеет, и не запрашивает вызов повторно ([ad38bcb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ad38bcb9edad39576056e8ce79e1e4e15978ee40))
* **web:** кнопки сборки гаснут без раннера, один тост на отказ и сброс «Идёт сборка…» ([df7bd0d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/df7bd0d5ecb9665ab03e8d32d4e3b446557d0fae))
* **web:** подпись события регистрации с passkey в журнале аудита ([ff651a5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ff651a5b33905a8cfe366ae64733dc2592fcef80))
* **web:** после регистрации с passkey переход на главную ([be1f747](https://github.com/AlexeyShalaev/hse-doc-studio/commit/be1f7472e1d8762fab9016d8aa7183015ed4e0b8))
* честное поведение сборки без раннеров (409 no_runners, доступность сборки, блокировка кнопок) ([e9718a3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e9718a386d3cac56559aa11810ac81b8c817042d))

## [0.3.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.2.0...v0.3.0) - 2026-11-02

- Shared server: teams can use the Studio together. Accounts and organisations, role-based project access, an installation admin area (/admin: people, sign-in and OIDC, mail, runners, queue, audit), builds on runners in isolated containers. Deploy with Docker Compose or Helm, see the Shared server section of the docs
- Collaboration: access links with a role, expiry, password and guest sign-in; invitations by e-mail or login, access requests and project ownership transfer; reviewers comment on the text and several people edit one document at the same time, seeing each other's cursors
- The Studio server as a git remote: the local Studio signs in to the server with a device code (device flow), sees the server's projects and clones and syncs them over git via HTTPS. Projects can be moved from the local Studio to the server together with their data
- Local Studio: automatic project sync with the server (on by default for projects obtained by signing in to a server, can be turned off per project) and PDF upload after a successful build, so supervisors and reviewers see the result without building
- Personal runners and AI providers: attach your own machine as a runner with a pairing code and build documents on it; the AI agent can work through your runner while your keys stay with you. Cloud builds on this machine are available right from the local Studio
- Quotas, AI gateway and runner autoscaling: limits on storage, builds per month, AI tokens per day and month and project members (installation default, organisation, user); when exhausted, choose low priority (default), reject or warn. The AI gateway records calls and fails over to another provider. The runner count can follow the queue automatically (webhook, compose or KEDA metrics); off by default
- Data autonomy: everything that grows has a retention period and background cleanup (audit 365 days, AI log 90, build logs 30 and so on; adjust them on the Data retention admin page). Audit and AI logs are split into monthly partitions, container logs are rotated, and when a disk reaches 90% a safe mode rejects large uploads while everything else keeps working
- Backups: schedule, full backup of the database, files and objects, server-side encryption, S3 or directory destinations (your own MinIO via one compose overlay), a connection test and failure alerts. Restore from the admin area with a preview, confirmation and maintenance mode, or with the hse-doc-studio backup restore command
- Self-diagnostics: the Self-diagnostics admin page checks the database, migrations, storage, disk, runners, queue, scheduler, TLS, backups and mail, explains the cause and suggests what to do; it alerts only on persistent problems. hse_diag_* metrics and a public /health/diagnostics
- Automatic server updates: release check every 6 hours, install by button or automatically in a maintenance window, backup and database snapshot first, image digest and cosign signature verification, automatic rollback if the new version does not come up. Default mode: notify only
- For administrators, upgrading: 0.2.0 was local-only, so there are no server installs on it and no database migration from 0.2.0 is needed: the server applies the whole chain on first start, from 0001 to dg_01_diagnostics (the latest being lc_02_partition_logs, bk_01_backups, up_01_server_updates, dg_01_diagnostics). Local 0.2.0 installs update with the Update button or update.sh / update.ps1 and their data is untouched. The server auto-updater installs only releases that ship an image-digest.json, i.e. 0.3.0 and later: it cannot install anything older, and when the digest is missing the run is cancelled (digest_missing) unless verification is set to None
- For administrators, environment and images: MinIO in compose is replaced with the pgsty/minio fork (web console restored, tag pinned); set S3_ACCESS_KEY and S3_SECRET_KEY, and keep SECRETS_KEY safe, since it encrypts secrets and backups. Auto-update is enabled by the updater profile: UPDATER_TOKEN in .env and docker compose --profile updater up -d (the service gets the docker socket, so it is off by default). New variables: HSE_STUDIO__SERVER_UPDATE__*, HSE_STUDIO__BACKUPS__*, HSE_STUDIO__LIFECYCLE__*, LOG_MAX_SIZE and LOG_MAX_FILE; see the variable reference for the full list. Off by default: automatic update installation (notify-only mode) and runner autoscaling; scheduled backups start working once a destination is added
- The code and tests run on Windows and macOS: fixed paths, directory permissions, encodings and network checks that broke running on those systems

## [0.2.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.3...v0.2.0) - 2026-10-26

- Master's programme: a 1st-year coursework template for System and Software Engineering — topic and application, report and slides
- Detached electronic signatures: freeze a PDF, sign it with an OpenPGP key or a qualified signature via the CryptoPro browser plug-in right in the Studio, or upload an existing signature. The Studio verifies it, adds an HSE-style signature stamp and builds the submission package
- Update a project to a new template version: project settings now have a Template version section. You see which files change before updating, your own edits are kept, conflicts are shown separately, and the update can be undone
- An available template update is flagged by a badge on Project settings, a dot in the outline, the status bar and a notification when you open the project
- A project saved by a newer Studio opens read-only, so an older version cannot accidentally damage its data
- New Topic and application document group, the academic supervisor's name fills the signature slot, and the Group field hint depends on the programme
- Dependencies and the base image updated, closing the vulnerabilities found in it

## [0.1.3](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.2...v0.1.3) - 2026-07-28

- The AI agent now works with any local model: if a model lacks tool support (e.g. phi3.5), it switches to a text protocol and keeps answering
- Agent errors are no longer lost — the failure reason shows up right in the chat
- Terminal updates: the update.sh and update.ps1 scripts run the same updater as the Update button — settings preserved, automatic rollback on failure
- Docs site polish: the banner always announces the current release; fixed the What's-new link, tab underline and buttons

## [0.1.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.1...v0.1.2) - 2026-07-28

- Fixed the app-error crash on the AI agent's very first reply (a duplicate router instance after a dependency update)
- The error screen now has a “Report an issue” button: it opens GitHub with the error, stack trace and version pre-filled — just add what you were doing

## [0.1.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.0...v0.1.1) - 2026-07-28

- The one-command install now also works in stock Windows PowerShell 5.1
- Install scripts speak English by default and Russian with HSE_STUDIO_LANG=ru; the docs pick the flag to match the page language
- A running local Ollama now registers itself as a provider — no more manual setup; the settings offer a one-click connect as well
- Every AI-agent tool is now translated in the tools menu: PDF reading, versions, projects, ask-the-user
- The data folder now ships with a ready-made projects directory — the project wizard suggests it right away

## 0.1.0 - 2026-07-28

- First release: a local studio for academic documents — projects from templates (thesis, coursework, Project Proposal) with every accompanying document and presentation
- One-click PDF builds: LaTeX runs inside a Docker container, nothing to install on your machine
- Code and visual editors with a built-in PDF viewer and text↔layout jumps (SyncTeX)
- GOST formatting checks: findings are anchored to source lines, many fix themselves automatically
- Submissions: the studio assembles the checkpoint package together with signatures and forms
- An AI assistant inside your project: bring your own provider (Claude, OpenAI and compatibles) or a local model via Ollama
- Project version history: timeline, diffs and restore — no git knowledge required
