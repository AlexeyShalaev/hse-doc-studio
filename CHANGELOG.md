# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.6.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.5.0...v0.6.0) (2026-11-04)


### Features

* **api:** настройка лендинга и корень сервера с тегами Open Graph ([a3776e2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a3776e20b4c11703a205cd501371eba8a411cc6d))
* **deploy:** публичный адрес S3 и режим доступа внешних раннеров в чарте и compose ([37a1b96](https://github.com/AlexeyShalaev/hse-doc-studio/commit/37a1b964f9c2f2dd0097e0651e4a8dc6f642a439))
* **devices:** люди в проекте: аватары в шапке, место, курсоры и расчёт нагрузки ([ffddacb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ffddacb3ee87441c5935acd6beb6258226f008df))
* **devices:** люди в проекте: сигнал вкладки, общий список онлайн и цвет человека одной функцией с курсором ([159fc6e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/159fc6e77f63c00a4f30366c8f669e51b211ddab))
* **devices:** присутствие подключённых Студий и статус сборок документов ([bf0c1a1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/bf0c1a1d0eef5e3d0e51754d2fcbc46233f514e9))
* **diagnostics:** предупреждение, когда есть раннеры вне сети, а публичного адреса S3 нет ([de0f918](https://github.com/AlexeyShalaev/hse-doc-studio/commit/de0f918f3f2728c4006e707ccf5bf88810725a0b))
* **storage:** ссылки на S3 по получателю: публичный адрес для раннеров вне сети и режим proxy ([f1bc687](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f1bc687cb653591136fc24d2787ceab39068799a))
* **web:** аватары людей в шапке проекта, место и переход к документу, подпись с именем у чужого курсора ([1dd96ff](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1dd96ff8c40bf042a8852360c1b1d19fc1b8453c))
* **web:** лендинг облака для не вошедшего человека ([2b7495b](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2b7495b083e3d8e8545aff96ca21bc5fb42a2fad))
* **web:** окошко уведомлений под колокольчиком ([acf3fc0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/acf3fc0a77845c20822f168c746d6d88c52c2167))
* **web:** окошко уведомлений под колокольчиком вместо перехода на страницу ([c51da19](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c51da194399b92a0494e7e3449d2331a279a4199))
* **web:** плашка и панель подключённых Студий, статус сборок, получение облачного PDF ([0708e3b](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0708e3b20fbf649b816ce5ff8968fec6f8d5a3a6))
* лендинг облака для не вошедшего человека ([1d7681e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1d7681eddc0814b0765c7bbfff90862bcaa104ee))
* подключённые Студии, ИИ через вашу машину и статус сборок с обеих сторон ([a818e96](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a818e96b42f7b6bd5e21bd24965309c052b4f329))


### Bug Fixes

* **api:** корень и картинка предпросмотра отвечают на HEAD ([9d9abf2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9d9abf217e1f667177065907ca9650f5daa529d9))
* **chat:** понятные причины сбоя модели за раннером и переполнения окна Ollama ([bfacc35](https://github.com/AlexeyShalaev/hse-doc-studio/commit/bfacc35997a4a657e8f6233ceb9378807d5b2e10))
* **git-sync:** кнопка «открыть репозиторий» ведёт на страницу проекта сервера Студии ([cf83c14](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cf83c14aad9dd0d1d396989e7c70b675e2d7344a))
* **git-sync:** ссылка на репозиторий ведёт на страницу проекта сервера Студии ([fa21697](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fa21697b56467737a77c1fc99df419a9cdc3a35c))
* **settings:** окно настроек выше и шире, меню шире ([f24065f](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f24065fb17dbbd9a219dc0c36d46511c260b34df))
* **settings:** окно настроек выше и шире, меню шире и не переносит названия ([042e93e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/042e93ea86b71c6baaff1a2d684da9c6720a9914))
* **storage:** публичный адрес S3 для раннеров вне сети сервера и режим proxy ([f49c8d9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f49c8d95f33e9b93be433df5c5241770b2b39810))
* **web:** контраст инициалов на аватарах и подписи у курсора: затемнение поверх цвета человека ([6f05e1d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6f05e1d6c75ae77f0a0d8860eb1d4ab91d3f0a98))

## [0.5.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.4.0...v0.5.0) - 2026-11-03

- Cloud projects in the local Studio: once connected to a server, the local Studio lists your cloud projects itself, in the same list as local ones and marked Cloud. One click on Open downloads the project into the projects folder (changeable in settings), shows the progress and opens it, with no clone wizard and no git on this path. The Open in local Studio link from the cloud takes you straight to the right project. Automatic sync and PDF upload need no setup and work for cloud projects from the start. If an open project is not linked to the cloud, the build panel says so: the PDF will stay on this computer
- Nicer e-mails: invitations, e-mail confirmation, password reset, address change, passkey notifications and project access e-mails now arrive designed, with a large button, a fallback link, a note on why you received it and a security block, along with a plain-text version. An e-mail is written in the recipient's account language (Russian or English) and the subject is translated too. In the admin area (Sign-in and registration) you can preview every e-mail in both languages and send a test one
- For administrators, one-button updates in Kubernetes: on the Updates page the Update and Roll back buttons now work in a cluster too. Turn it on with the updater.enabled flag in the Helm chart (off by default) and HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes: a separate pod changes the api Deployment image, runs migrations as a Job and waits for health, and the image is checked against the digest from the release. Permissions are limited to its own namespace. A backup runs first if one is configured, otherwise you must confirm the risk. If migrations were applied but the new version did not come up, the image is not rolled back automatically: the status is Needs hands, with ready commands. After such an update set the version in your values (image.tag), otherwise the next helm upgrade will bring the old image back
- Fixes: in the dark theme the answer options in the welcome questionnaire were black on dark and unreadable; the settings sidebar did not scroll, so lower sections (such as AI clients (MCP)) were out of reach, and the AI group heading was shown twice; on the server every start logged a local Ollama sync error
- For administrators, upgrading from 0.4.0: there are no database migrations in this release, the schema stays at pk_01_passkeys. New settings: updater.enabled in Helm (off by default), HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes, and for the local Studio the cloud projects folder (Settings, Repository access). E-mails are sent as HTML together with a plain-text version: without SMTP nothing changes and links are still shown on screen

## [0.4.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.3.0...v0.4.0) - 2026-11-03

- Passkey sign-in: sign in with a fingerprint, Face ID or a hardware key instead of a password. Keys are added and removed in the profile, sensitive actions ask you to confirm your identity again, and an admin can reset a person's keys. An invitation to a specific address lets the person create an account with a key right away, with no password; an e-mail is sent when a key is added or reset. The admin people list shows the number of keys
- MCP: AI clients (Claude, Cursor and others) work with the Studio over the Model Context Protocol, both in the cloud at /mcp and in the local Studio on localhost. 51 actions are available: projects, files, builds, checks and the norm-control report, requirements, review comments and history. It works with a personal token carrying the MCP permission; dangerous actions are off by default, an admin turns each one on or off in the installation settings, and e-signatures are not available over MCP. For a local client there is the hse-doc-studio mcp bridge. See the AI clients (MCP) section for setup
- In-app help: articles with screenshots and short videos in Russian and English, in light and dark themes. Onboarding for new people: a short questionnaire and a guided tour that highlights interface elements on a demo project (creating a project, editing, AI, git) without risking your data; it can be run again
- Local version from the cloud: the server has a Local version page explaining how to download and install the local Studio and connect it to this server; installers run with HSE_STUDIO_CONNECT open the connection screen straight away. The server is checked before connecting
- Builds without runners: instead of a 503 error the Studio plainly says there are no cloud runners, blocks the build buttons and suggests building the document locally. The same applies when no runner has the required tags
- For administrators, runners in Kubernetes: in the Helm chart runner.executor=kubernetes starts a pod per build in its own namespace (permissions on pods only, with a NetworkPolicy), so the node's docker.sock is not needed. The default is still docker
- For administrators, upgrading from 0.3.0: the server applies the new migrations on first start (ob_01_user_onboarding, pk_01_passkeys), no manual steps are needed. New settings: passkey sign-in (admin → Sign-in, or HSE_STUDIO__AUTH__PASSKEYS_ENABLED; HSE_STUDIO__AUTH__PASSKEY_RP_ID for a shared parent domain of keys) and MCP (admin, off by default). If you change the server address public_url, existing passkeys stop working

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
