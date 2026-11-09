# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.17.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.16.0...v0.17.0) (2026-11-09)


### Features

* **admin:** group build-all jobs into one batch row in the queue ([f19ef18](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f19ef189d12172c1ec67ee2d59d86435a2bbd125))
* **admin:** say that removing an install revokes the runner, show rollback ([fed9ed2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fed9ed2e80f90c876ef608941a8b83f637f42cbf))
* **admin:** say when the runner is back on the previous version but offline ([63d6c30](https://github.com/AlexeyShalaev/hse-doc-studio/commit/63d6c305624c7214add08a2f1b5d86ba4569bb3e))
* **admin:** офисные задачи на экране изоляции раннеров ([f4fffd8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f4fffd8056d4f14c05966d10550346c7ff98ab84))
* **helm:** runner.installFromUi.buildNamespace for build pods of admin-installed runners ([b6dd453](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b6dd453ce976c960a59a653343bd73a0a74b6a28))
* **helm:** встроенный Gotenberg для офисных задач раннеров ([b4ccc62](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b4ccc62768b41482501b76804a561c3dab8d5d26))
* **invitations:** готовый текст приглашения из данных проекта ([7795526](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7795526324de6124b48d620775c85b7c4eaa61c5))
* **mcp:** compile_document с wait и ожиданием до 45 с вместо таймаута клиента ([c5165fc](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c5165fc01bd3e3251fe283d2b6cf8ebe2b5d555c))
* **mcp:** git_sync как кнопка синхронизации, с итогом и списком конфликтов ([b8e58ca](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b8e58caca0956b9fe07278e343504872d605fa97))
* **mcp:** list_project_fields and unset in set_project_meta ([1336298](https://github.com/AlexeyShalaev/hse-doc-studio/commit/13362988274b139cb4cb3cadb2d4a62a973a162d))
* **mcp:** set_document_variant through the same document update as the settings ([03c5053](https://github.com/AlexeyShalaev/hse-doc-studio/commit/03c50531eda4c632f596acd886699ee10a798e56))
* **mcp:** set_project_people edits one author by slug, author e-mail and academic supervisor ([e56e2f8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e56e2f8b7a6efd68270e4f47bc059c754915bcd1))
* **mcp:** template update status, plan and apply tools ([d27efb6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d27efb64ba27cde74dd51e15aef4bd5d89030060))
* **mcp:** доступ к проекту: участники, приглашение по почте, отзыв ([69c246a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/69c246ad49520686f8c2104aed683d2dfefaf073))
* **runner-install:** own namespace for build pods of admin-installed runners ([8068dc1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8068dc12e182aeeb4c94d7a496759b76afad4376))
* **runner-install:** revoke the runner on remove, roll back failed updates ([ab022d1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ab022d1b8096973cc24bbea8542522c69cea7c84))
* **runner-install:** wait for the runner on the previous version after a rollback ([c2e5b10](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c2e5b10c42434ee3350c8d28a7aca00358860c40))
* **runner-install:** адрес Gotenberg раннерам из админки ([64bc592](https://github.com/AlexeyShalaev/hse-doc-studio/commit/64bc592b28171f7d41baef696a16bf28a207a2dd))
* **signatures:** комплект для LMS по плану подписей и MCP-инструменты подписи ([730bdaa](https://github.com/AlexeyShalaev/hse-doc-studio/commit/730bdaa25fd30320ac7e2e6be2f0ce82df85824f))
* **signatures:** план подписей документа и счётчик точки сдачи по нему ([0155a16](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0155a165b80da5451ac902439d852fb3ce24045b))
* **signatures:** подписать комплект, PAdES над зафиксированным PDF и права на слоты ([6df6c77](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6df6c7788f37f9b6d28bad27e3c4dbf7879b2f3e))
* **templates:** опись вшитых паков и распознавание подключённого каталога шаблонов ([cb5c91a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cb5c91a41a88f51238d188823d5eb8e13b58c34c))
* **web:** заранее составленное сообщение в форме приглашения ([6ab0c85](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6ab0c853477cae31852f81a08be4a024a779872d))
* **web:** сборка, прерванная перезапуском сервера, показана как «прервана» ([fceca30](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fceca301bc59388f87a4983665bd811313709fef))
* свой namespace подов сборки раннеров из админки ([611116d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/611116d32c52118e27b159c7adc7366136c4da08))


### Bug Fixes

* **admin:** classify the batch cancel route as admin-only ([f3b2cb5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f3b2cb59a97da2fadcb7c9504f53b541bc5375ab))
* **checks:** skip inactive \if branches in document-scope python checks ([5ea0d2c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5ea0d2c9e8136623e90ba581a09fe1891f4a55e5))
* **checks:** плейсхолдеры в выключенных ветках редакции не считаются ([ed42a7e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ed42a7e34085926b198188372a017b97b5007962))
* **compile:** облачная сборка переживает перезапуск api ([8d5d6b7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8d5d6b7947744b872c778dc64540f76f213c1969))
* **helm:** короче окно недоступности api при выкатке ([8028c57](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8028c57503eb2040734dfdea604706bbf6078475))
* **jobs:** tell busy runners from missing ones and drop builds nobody can take ([8cec060](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8cec0600246ea1460922dc106e1b193552dea58b))
* **mcp:** clone_cloud_project ждёт по умолчанию 45 с, меньше таймаута клиента ([311b0c6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/311b0c629c19ba554714e346cf2f03c70742fb4a))
* **projects:** называть отставший каталог шаблонов вместо совета обновить Студию ([fc90134](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fc90134b2889fc45847695ba3432541d5523a942))
* **runner-install:** check whether a replacement applied when the response is lost ([e2724d9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e2724d9047e044297e2f8f2e0962817a49263528))
* **update:** не переносить привязку паков dev-сборки на опубликованный образ ([65cc839](https://github.com/AlexeyShalaev/hse-doc-studio/commit/65cc8397df02ceb6f3663283fa706404b6cc95f9))
* **web:** меню «⋯» и подсказки поверх окна настроек ([4f8469c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4f8469cd88b6cfc6cf01bbae32170ed27a5cb15e))
* **web:** правдивый текст при отставшем каталоге шаблонов и предупреждение при обновлении ([43658ed](https://github.com/AlexeyShalaev/hse-doc-studio/commit/43658ed4bab472ee6636bbfffb026e467d6935fc))
* облачная сборка переживает перезапуск api, мягкая остановка ([671b4de](https://github.com/AlexeyShalaev/hse-doc-studio/commit/671b4de65b2842b2b746a7c7c9f6a565fb4ba2ad))


### Performance Improvements

* **jobs:** read route settings once per stranded-jobs sweep ([2f6bbac](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2f6bbac1ec723121d7c12d913e7210c8a48c4e84))

## [0.16.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.15.0...v0.16.0) - 2026-11-08

- In-place update of admin-installed runners: a runner installed from the admin area in Kubernetes or Docker is updated to the Studio version without removing and reinstalling it. The name, token, data volume and install limits are kept, the manifest is applied with the current isolation rules, progress is shown step by step, and the update is written to the audit log. The chart adds the update permission on Deployments.
- Admin-installed runners are managed on the Runners page: Update and Remove install in the Actions menu, an Update to vX button for outdated runners, and a separate block for installs whose runner is already revoked.
- The local Studio no longer offers to fetch cloud builds of documents that are not produced as PDF (such as pptx), and build fetch failures now show specific messages instead of a generic connection error.

## [0.15.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.14.0...v0.15.0) - 2026-11-08

- Runner details in the admin area: where each runner runs (Kubernetes pod, container or host) and how it builds documents (Docker or Kubernetes), its CPU, memory and storage limits, and a cluster isolation panel. The panel shows the policies declared in Helm and, with runner.isolationInfo.readCluster enabled, what actually exists in the cluster: NetworkPolicy, ResourceQuota, LimitRange and Pod Security labels.
- MCP: create_project no longer asks for a folder in the cloud, the new set_project_people tool sets the project supervisor and members (recorded in the audit log), and clone_cloud_project in the local Studio clones a project from the cloud.
- Kubernetes builds no longer fail with idle_timeout after the PDF is ready: word and character counting is time limited, and if it hangs the build still succeeds with a warning.
- Local Studio linked to the cloud: the server version is refreshed on sync, a last build id that this Studio does not have is no longer returned, and documents without a PDF (such as pptx) no longer fail PDF autopublish.
- SPI coursework template 2026.1.2: the topic application matches the official 2026 form, names are shown as "Surname I.O.". The released 2026.1.1 is unchanged.

## [0.14.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.13.0...v0.14.0) - 2026-11-07

- Roll back to an earlier version from the admin area: a list of published releases, each with a verdict on database schema compatibility. A rollback is allowed only to a version with the same migration state, a backup is taken first when configured, and if the version does not come up the system returns to the previous image. Requires an updated updater.
- Auto-install switch for updates: while it is off, new versions are not installed on their own, but checks and notifications continue. After a successful rollback auto-install switches to notify-only mode. Rollbacks and toggles are written to the audit log.
- Limits and isolation for Kubernetes runners: requests and limits for CPU, memory and storage on runners and build pods (set in Helm and in the install form in the UI), clear failure reasons for out-of-memory and storage overruns, deny-all network traffic for build pods, optional runner egress policies, ResourceQuota and LimitRange, stricter pod security settings and reduced Studio permissions. Already installed runners stay unchanged until reinstalled.

## [0.13.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.12.0...v0.13.0) - 2026-11-07

- Model servers: the admin area has a new Model servers page. It installs Ollama, vLLM or SGLang on the machine that runs Studio, or on another one over SSH (one-time password or key, with an offer to save the access encrypted). It shows the API address and key. By default a server listens on the loopback interface only; vLLM and SGLang are exposed publicly only with an API key and after confirmation. For gated models a Hugging Face token is set in settings. In Helm, installing on the same machine is off by default (modelServers.local.enabled).

## [0.12.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.11.0...v0.12.0) - 2026-11-07

- Installing a runner with a single command: creating a token now shows a ready docker run line and a script that installs the runner as a service (systemd on Linux, launchd on macOS). The script contains no secrets and supports a dry run, status and uninstall.
- Installing a runner on the same machine as Studio from the admin area: as a container in Docker, or as a separate restricted Deployment in Kubernetes (off by default in Helm, value runner.installFromUi.enabled).
- Installing a runner on other machines over SSH from the admin area: host key fingerprint confirmation, password or key with passphrase, a plan and step-by-step progress. Credentials are one-time by default; you can optionally save them encrypted for updates and reinstalls. Internal networks stay blocked until the address is added to HSE_STUDIO__RUNNER_INSTALL__SSH_ALLOWLIST.
- For administrators: the server applies the new migration on first start (ri_01_runner_ssh_credentials), no manual steps are needed. SSH installation requires asyncssh (included in the server build).

## [0.11.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.10.0...v0.11.0) - 2026-11-06

- "Build all" no longer leaves jobs queued forever when the personal runner is busy and there are no shared runners: jobs wait for a free slot on the personal runner. Jobs that are already stuck are picked up on the runner's next poll.
- Self-diagnostics: every problem row can be opened to reach the page where it is fixed, for example a queue failure leads to the runners queue tab and backups lead to the backups page.
- Settings, Disk: Studio offers to clean up old system versions (images of earlier versions, stale tags of helper images, the stopped updater). The latest previous version kept for rollback is protected from bulk cleanup.

## [0.10.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.9.0...v0.10.0) - 2026-11-06

- A stale tab after an update no longer breaks the admin area: the app picks up the new version and offers to reload the page.
- The build queue shows real phases (queued, building), and the "Build is not responding" warning counts from the actual start, not from the click.
- Stopping a build in the cloud is synced with the local Studio and back: the status updates in both places.
- Warnings about missing backups and public runners can be acknowledged on purpose, and they stop nagging.
- The documents panel and the agent chat no longer overflow at narrow widths and large text sizes: buttons, labels and the model picker fit.

## [0.9.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.8.0...v0.9.0) - 2026-11-05

- The topic application and the presentation build without supervisor or author data: the new course project template version 2026.1.1 fixes the There's no line here to end error that broke the build when a signature field was empty. New projects are created on it right away, existing ones see it as a recommended small update: accept it in the project settings
- Cloud builds on a personal runner get the same fonts as local builds: Times New Roman, Arial and Consolas, which the local Studio takes from your computer when the runner connects if the fonts folder is empty. For a shared runner and a runner in Kubernetes the fonts folder is set by a setting (a volume). Microsoft fonts are not shipped with the Studio or its images. If a template asks for a font directly and it is missing, the build fails with a clear font missing reason and the font name
- Fixed a false upload error: when Build all started several builds of one project, the second build could delete the first one's finished PDF and the first reported that the result could not be uploaded. The result is now copied aside before uploading, and if the file really is missing the reason is named PDF not received. A failed build also no longer shows an endless Build is not responding warning and the Stop build button
- Text size: the step you pick no longer snaps back to the account value. Before, choosing 100 % right after 140 % could roll back until the save reached the server. Now an explicit choice on the device always beats the account value and is saved to the account, retrying on error
- For administrators, upgrading from 0.8.0: no database migrations. New runner settings: HSE_RUNNER__FONTS_DIR, HSE_RUNNER__FONTS_HOST_DIR and HSE_RUNNER__FONTS_MOUNT_TARGET (Docker runner), HSE_RUNNER__K8S__FONTS_CLAIM and runner.kubernetes.fonts.existingClaim in Helm (Kubernetes runner). Template 2026.1.1 is used automatically for new projects

## [0.8.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.7.0...v0.8.0) - 2026-11-04

- Text size: in Settings, Appearance you can choose the interface text size (90, 100, 112, 125 or 140 %). It changes at once across the whole app (menus, forms, dialogs, the editor, the admin area, the landing page), is remembered in your account and applies without flicker on load. Document content and the PDF page are not scaled. On a phone the 90 % step does not shrink buttons and fields below a comfortable size
- A failed build explains itself: the Build tab shows the failure code and reason, what to do and a Build again button, and the document list and the Now block show the reason under the name. The build log now reaches the cloud (before it was empty even for successful builds), including live, and refusals before start (no Docker, TeX image or runner) are recorded as a failed build. Reasons are named in plain words: no output for too long, no disk space, the result could not be uploaded to storage and others. The build silence timeout is raised from 120 to 300 seconds: the first build on a fresh font cache can stay quiet for a long time
- Presentations and other office documents in the cloud through your Studio: if Docker runs on your computer and the Gotenberg image is pulled (docker pull gotenberg/gotenberg:8), the local Studio tells the cloud it can convert, and the Build button for presentations and Word documents is no longer blocked. Without Docker or the image the previous explanatory message stays
- For administrators, upgrading from 0.7.0: the release has one database migration (cf_01_compile_failure, two optional columns in the build record), the server applies it itself on first start, take a backup before updating. New settings: HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S (300 seconds by default) and HSE_RUNNER__TEX_IDLE_TIMEOUT_S for the runner. Runner build logs are kept on the api volume (meant for a single api replica)

## [0.7.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.6.0...v0.7.0) - 2026-11-04

- Mobile cloud version: the Studio is comfortable on a phone from 360 px. Dialogs and menus open as bottom sheets, tables become cards, input fields no longer zoom the page in iOS, buttons are at least 40 px, and the screen notch and on-screen keyboard are accounted for. Sign-in, the landing page, the home screen with the project list and filters, the inbox and Studio connection all work
- The project workspace on a phone: a bottom bar of sections (documents, remarks, submission, files, more), a project header with people online, connected Studios and sync, an editor with a scrollable toolbar and a distraction-free mode while typing, a PDF with zoom by buttons and pinch, and the agent chat full screen. Settings and the admin area also work well on a phone: sections in a sheet, single-column forms and tables as cards
- Not yet working on a phone: the ONLYOFFICE editor, side-by-side mode, keyboard shortcuts (the command palette and help are in the account menu), drag-and-drop of files into the window, CryptoPro signing and the onboarding tour with highlights. Tablets keep the desktop layout. The mobile version was tested on emulation, please report anything you find on real devices
- Fixes: the Help window opened from the account menu crashed on a phone; the Signatures and Authors pages of a project were clipped on narrow screens
- For administrators, upgrading from 0.6.0: this release has no database migrations and no new required settings, only the interface changes

## [0.6.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.5.0...v0.6.0) - 2026-11-04

- Cloud landing page: someone who opens the server address and is not signed in sees a page describing the Studio (who it is for, what it does, how to start, security) with the sign-in form right on it. The link to the cloud can be shared: messengers show it with a title, a description and a picture. Invitations, password reset, OIDC and passkey sign-in work as before. An administrator can turn the landing off in the installation settings, then the sign-in page opens straight away
- Connected Studios: a cloud project shows which of your local Studios are connected, whether they are online (or when they last were), the version, project sync, PDF upload, the state of your personal runner and of AI through your machine. The local Studio shows the same the other way round: the link to the cloud, what the cloud sees, who else is online in the project. For each document you can see where and when it was built and whether the build is current. A cloud PDF can be fetched into the local Studio with the Get build button, and with automatic sync on it is fetched by itself. The cloud has a My Studios list with a Forget device button. Only state metadata is sent: no paths, contents or keys
- People in the project: the project header shows avatars of members who are online right now, with a caption of what and where they are doing (editing the Application, viewing remarks, working locally) and a jump to the same document. Another person's cursor in a document shows their name, and the cursor colour matches their avatar. Members see each other in the browser and in the local Studio, guests with an access link are not listed. The load is minimal: one light signal a minute per person, nothing written to the database
- Bell and settings: the bell opens a small window with the latest notifications, a mark-as-read action and a Show all link instead of going to a page. The settings window is taller and wider, its menu scrolls and section names no longer wrap. When a local Studio cannot use AI through its runner, the reason and what to do are now shown, and the cloud has an Add in the cloud button for the Through my runner provider
- For administrators, runners outside the server network and storage: personal runners and browsers get S3 links at a public address. Set it with s3.publicEndpoint in Helm (HSE_STUDIO__S3__PUBLIC_ENDPOINT); the storage has to be published under its own name with TLS (see the runners section). Without a public address a cloud build on a runner outside the network fails with a clear storage_unreachable error and the self-diagnostics page warns. A fallback without publishing the storage: s3.outsideRunnerAccess: proxy, results go through the server
- For administrators, upgrading from 0.5.0: the release has one database migration (cd_01_connected_devices, connected devices and build data), the server applies it itself on first start, take a backup before updating. New settings: s3.publicEndpoint, s3.outsideRunnerAccess, s3.sharedRunnersOutside (Helm), HSE_STUDIO__SERVER__LANDING_ENABLED and the landing switch in the admin area. Fixed: for a cloud project the open repository button led to a 404 page, now it opens the project page

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
