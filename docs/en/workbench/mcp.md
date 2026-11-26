---
title: AI clients (MCP)
description: Connect Claude, Codex, Cursor, Gemini CLI and other AI clients to the Studio over the Model Context Protocol, locally and in the cloud.
tags:
  - Workbench
  - AI agent
---

# AI clients (MCP)

<p class="hds-lede">The Studio can act as a Model Context Protocol server. An external AI client (Claude Code, Claude Desktop, Codex, OpenCode, Gemini CLI, Cursor, VS Code, Windsurf, Zed, Cline, JetBrains) sees your projects and works in them with the Studio's tools: it reads and edits files, builds PDFs, goes through findings and saves snapshots. It acts on your behalf and can do no more than you can.</p>

## Turn it on

=== "Local Studio"

    **Settings → AI clients (MCP) → “Enable the MCP server”**. The server address is `http://127.0.0.1:17240/mcp`, the Studio's own port. No token is needed: the server only answers programs on this computer and rejects requests whose `Host` or `Origin` names another site.

=== "Cloud Studio"

    An administrator turns MCP on: **Admin → MCP server → “Enable the MCP server”**. Then everyone issues a token: **Settings → Account → Tokens → New token**, permission **MCP**. The server address is `https://<Studio address>/mcp`; the token goes in the `Authorization: Bearer <token>` header.

    If you already have a token, there is no need for a new one: **Settings → Account → Tokens → “Edit permissions”** on that token (see [Token permissions](#scopes)).

### Token permissions { #scopes }

A token can do what its permissions allow. MCP needs the **MCP** permission; **Signing via MCP** lets `sign_submission` sign a submission, **Template Studio** opens the `pack_*` tools, **MCP: administration** opens the admin tools (instance administrators only).

You can change the permissions of an existing token: **Settings → Account → Tokens → “Edit permissions”**. Tick what you need, check the “Will be added” and “Will be removed” summary and save. The token itself stays the same, so nothing changes in the CLI, scripts or AI clients.

- New permissions apply right away, from the next request with this token. A removed permission stops working right away too.
- An AI client remembers the tool list when it connects. To see new tools (or stop showing removed ones), reconnect the Studio server in the client (`/mcp` in Claude Code, the server restart button in Cursor and VS Code) or restart the client. The Studio runs MCP without sessions, so it cannot tell the client about the change itself.
- Only a person signed in to the Studio in a browser can change permissions. A token cannot change its own or another token's permissions, neither through MCP nor through the API.
- You can give the same permissions as when issuing a token: **MCP: administration** only to an instance administrator, only git permissions to a device token (sign-in with a code). Any permission can be removed.
- An expired token cannot be changed; issue a new one. A revoked token no longer exists.
- Every change is recorded in the audit log: what was added and what was removed.

## Connect a client

Ready-made configs with your address are in the Studio: **Settings**, section **AI clients (MCP)**; pick the client from the list. Below are the same configs for the cloud with the address `https://studio.example.org/mcp`. For a local Studio the address is `http://127.0.0.1:17240/mcp`; drop the `Authorization` header, the token variable and `bearer_token_env_var`.

### Token in an environment variable

Where a client can substitute an environment variable, the config refers to `HSE_STUDIO_TOKEN`, so the token is not stored in the file as plain text. Set the variable before starting the client:

=== "macOS, Linux"

    ```bash
    # in ~/.zshrc or ~/.bashrc
    export HSE_STUDIO_TOKEN=hsd_pat_...
    ```

    An editor started from the Dock or a menu does not see shell variables: start it from a terminal (`cursor .`, `code .`).

=== "Windows"

    ```powershell
    setx HSE_STUDIO_TOKEN hsd_pat_...
    ```

    `setx` applies to new windows and programs: restart the terminal and the editor.

### Terminal agents

=== "Claude Code"

    ```bash
    # local
    claude mcp add --transport http hse-doc-studio http://127.0.0.1:17240/mcp
    # cloud
    claude mcp add --transport http hse-doc-studio https://studio.example.org/mcp \
      --header "Authorization: Bearer hsd_pat_..."
    ```

    [Claude Code docs](https://code.claude.com/docs/en/mcp)

=== "Codex"

    The CLI, the IDE extension and the desktop app share `~/.codex/config.toml` (on Windows it is in the user folder, `%USERPROFILE%\.codex\config.toml`).

    ```bash
    codex mcp add hse-doc-studio --url https://studio.example.org/mcp \
      --bearer-token-env-var HSE_STUDIO_TOKEN
    ```

    The same by hand in `config.toml`:

    ```toml
    [mcp_servers.hse-doc-studio]
    url = "https://studio.example.org/mcp"
    bearer_token_env_var = "HSE_STUDIO_TOKEN"
    ```

    Check: `codex mcp list`, or `/mcp` in a session. [Codex docs](https://developers.openai.com/codex/mcp), [`codex mcp add` flags](https://developers.openai.com/codex/cli/reference).

=== "OpenCode"

    The file is `opencode.json` at the project root, or `~/.config/opencode/opencode.json` for every project.

    ```json
    {
      "$schema": "https://opencode.ai/config.json",
      "mcp": {
        "servers": {
          "hse-doc-studio": {
            "type": "remote",
            "url": "https://studio.example.org/mcp",
            "oauth": false,
            "headers": { "Authorization": "Bearer {env:HSE_STUDIO_TOKEN}" }
          }
        }
      }
    }
    ```

    The command writes the same to the project config (`--global` for the shared one):

    ```bash
    opencode mcp add hse-doc-studio --url https://studio.example.org/mcp \
      --header 'Authorization=Bearer {env:HSE_STUDIO_TOKEN}'
    ```

    `oauth: false` turns off the OAuth sign-in attempt: the Studio takes a token. In OpenCode 1.x the server sits directly under `mcp`, without `servers`. [OpenCode docs](https://opencode.ai/docs/mcp-servers/)

=== "Gemini CLI"

    ```bash
    gemini mcp add --scope user --transport http \
      --header 'Authorization: Bearer ${HSE_STUDIO_TOKEN}' \
      hse-doc-studio https://studio.example.org/mcp
    ```

    Or by hand in `~/.gemini/settings.json` (for a project, `.gemini/settings.json`):

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "httpUrl": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer ${HSE_STUDIO_TOKEN}" }
        }
      }
    }
    ```

    It has to be `httpUrl`: in Gemini CLI the `url` field means the old SSE transport. Single quotes in the command keep the shell from writing the token into the file. [Gemini CLI docs](https://geminicli.com/docs/tools/mcp-server/)

### Editors

=== "Cursor"

    The file is `~/.cursor/mcp.json` or `.cursor/mcp.json` in the project.

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "url": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer ${env:HSE_STUDIO_TOKEN}" }
        }
      }
    }
    ```

    [Cursor docs](https://cursor.com/docs/mcp)

=== "VS Code"

    Copilot reads `~/.copilot/mcp-config.json` or `.mcp.json` at the project root. The easiest way is the **MCP: Add Server** command.

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "type": "http",
          "url": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer ${HSE_STUDIO_TOKEN}" },
          "tools": ["*"]
        }
      }
    }
    ```

    VS Code still understands the old `.vscode/mcp.json` format with the `servers` key, but does not recommend it for new setups. [VS Code docs](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)

=== "Windsurf"

    Windsurf is now called Devin Desktop. The file is `~/.config/devin/mcp_config.json`, on Windows `%APPDATA%\devin\mcp_config.json`; **Open MCP config file** in the MCP menu opens it. Older Windsurf versions use `~/.codeium/windsurf/mcp_config.json`.

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "serverUrl": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer ${env:HSE_STUDIO_TOKEN}" }
        }
      }
    }
    ```

    After editing, refresh the server list. [Windsurf docs](https://docs.devin.ai/windsurf/plugins/cascade/mcp)

=== "Zed"

    The settings file is `~/.config/zed/settings.json`, on Windows `%APPDATA%\Zed\settings.json`. You can also enter it in **Settings | AI | MCP Servers**, **Add Remote Server**.

    ```json
    {
      "context_servers": {
        "hse-doc-studio": {
          "url": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer hsd_pat_..." }
        }
      }
    }
    ```

    The Zed docs do not describe variables in `headers`, so the token goes into the file. [Zed docs](https://zed.dev/docs/ai/mcp)

=== "Cline"

    In the extension: the **Configure** tab, the **Configure MCP Servers** button. Cline CLI uses `~/.cline/data/settings/cline_mcp_settings.json`.

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "type": "streamableHttp",
          "url": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer hsd_pat_..." }
        }
      }
    }
    ```

    Without `"type": "streamableHttp"` Cline falls back to the old SSE, which the Studio does not serve. From a terminal:

    ```bash
    cline mcp add hse-doc-studio https://studio.example.org/mcp --transport http \
      --header "Authorization: Bearer hsd_pat_..." --yes
    ```

    The Cline docs do not describe variables in `headers`. [Cline docs](https://docs.cline.bot/mcp/adding-and-configuring-servers)

=== "JetBrains"

    **Junie** (plugin and CLI) reads `~/.junie/mcp/mcp.json` or `.junie/mcp/mcp.json` in the project:

    ```json
    {
      "mcpServers": {
        "hse-doc-studio": {
          "url": "https://studio.example.org/mcp",
          "headers": { "Authorization": "Bearer hsd_pat_..." }
        }
      }
    }
    ```

    **AI Assistant**: **Settings | Tools | AI Assistant | Model Context Protocol (MCP)**, the **Add** button. For a remote server its docs describe only `url`, with no headers. That is enough for a local Studio (`{"mcpServers": {"hse-doc-studio": {"url": "http://127.0.0.1:17240/mcp"}}}`); for the cloud use the stdio bridge below. [Junie docs](https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html), [AI Assistant docs](https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html)

### Clients that launch a process (stdio)

Claude Desktop and clients that launch the server as a process use the `hse-doc-studio mcp` bridge, which forwards requests to a running Studio.

```json
{
  "mcpServers": {
    "hse-doc-studio": {
      "command": "hse-doc-studio",
      "args": ["mcp", "--url", "https://studio.example.org"],
      "env": { "HSE_STUDIO_TOKEN": "hsd_pat_..." }
    }
  }
}
```

Without `--url` the bridge connects to the local Studio, which must be running. If the `hse-doc-studio` command is not installed, [`mcp-remote`](https://github.com/geelen/mcp-remote) does the same (needs Node.js): `"command": "npx"`, `"args": ["-y", "mcp-remote", "https://studio.example.org/mcp", "--header", "Authorization:${AUTH_HEADER}"]`, `"env": { "AUTH_HEADER": "Bearer hsd_pat_..." }`.

### Clients that need OAuth

ChatGPT (apps and connectors), Claude on the web and on phones (connectors) and other cloud clients reach the server from their own servers and sign in only with OAuth or with no authentication. The Studio accepts only a token in a header for now, so these clients cannot connect, and a local Studio is not visible to them at all.

What you can do instead:

- **ChatGPT**: connect the Studio to Codex. Its `~/.codex/config.toml` is shared by the CLI, the IDE extension and the ChatGPT desktop app.
- **Claude**: Claude Desktop works through the stdio bridge, Claude Code connects directly.

## What is available

- **Tools.** Projects (list, card, create, metadata, supervisor and authors, template update, access and invitations in the cloud), files (tree, read, search, edit, write, move), builds (run and wait for the result, history, log, cancel), checks and the normcontrol report, requirements, review comments (cloud), history and git sync, submission profiles and packages, signature status, the signing route (cloud), packs in the Template Studio. Project tools take `project_id`; start with `list_projects`.
- **Resources.** `studio://projects`, the project card `studio://projects/<id>`, files `studio://projects/<id>/files/<path>` and build PDFs.
- **Prompts.** `fix_build`, `normcontrol` (go through findings), `review_changes` (describe changes before a snapshot).

### Projects: creation, people, a project from the cloud

- **`create_project`** creates a project from a template (`pack_id`, `template_id`, `version` from `list_templates`). The local Studio needs `folder`, the full path to a new folder. In the cloud the server picks the folder: the schema has no `folder` field, and a value sent anyway is not used.
    - It runs the same scenario as the web creation wizard, with the same checks. Authors go in `authors`: `name` (full name, required), `group`, `email`, and for a team project also `topic` (the author's topic), `slug` (the author's folder) and `managed` (whether the author's file set is kept here, yes by default). For a single author `author_name` still works.
    - More than one author means a team project (`staffing: "team"`), as in the wizard. `list_templates` shows whether a template supports teams (`staffing=solo,team`). Every managed author needs a topic, at least one author must be managed, and `slug` is derived from the surname by default and must be unique. Each managed author gets their own instances of personal documents (`<document>--<slug>`) in their folder; the team's shared documents are kept unless `shared_enabled` is `false`.
    - The supervisors `supervisor`, `co_supervisor` and `academic_supervisor` are optional and take the same fields as in `set_project_people`; they can be set later as well. The group of the first author who has one goes to `meta.group`, as in the wizard.
    - The reply has the project id and, for a team project, the authors' `slug` values: `set_project_people` picks an author by them.
    - Example: `{"name": "Inventory system", "pack_id": "hse-cs-se", "template_id": "vkr", "version": "2026.1", "kind": "project", "authors": [{"name": "Smirnova Anna", "topic": "Backend"}, {"name": "Petrov Boris", "topic": "Client"}], "supervisor": {"name": "S. A. Shershakov"}}`.
- **`set_project_people`** changes the supervisor (`supervisor`), co-supervisor (`co_supervisor`), academic programme supervisor (`academic_supervisor`) and authors, which go to the title page, the application and the statement. The rights are those of the project settings: a role that may change settings, and a project that is writable. The values reach the PDF on the next build: `common/meta.tex` is regenerated before every build.
    - A supervisor has `name`, `title` (position), `degree` (academic degree or rank) and `role` (`university` or `company`). Fields you pass replace the current ones, the rest stay; an empty string clears the position or degree, an empty `name` removes the person from the project.
    - `author` changes one author and leaves the others alone: `name`, `group`, `email`, `topic` (the topic in a team project); an empty string clears the group, e-mail or topic. In a team project the author is picked by `slug` from `get_project`, in a solo project the first author changes.
    - `authors` replaces the whole list: `name`, `group`, `email` and `topic` of each author, the first one goes to the title page. To keep the topic and file set of existing authors in a team project, pass their `slug` from `get_project`. A new author in a team project comes without a file set (`managed: false`), as when an author is added in the settings; the set is turned on in the project settings.
    - `clear: ["co_supervisor"]` removes the co-supervisor (`supervisor` and `academic_supervisor` work the same way).
    - Example: `{"supervisor": {"name": "S. A. Shershakov", "degree": "PhD"}, "author": {"group": "MPI251", "email": "ivanov@edu.hse.ru"}}`.
    - Every change is audited: in the cloud as a `project.people_update` event with the old and new values; locally the call is in the MCP log.
- **`clone_cloud_project`** (local Studio only) downloads a project from a cloud Studio, like the “Open” button of a cloud project in the list. Pass the project `url`, such as `https://studio.example.org/projects/<id>/`, or `project_id` if the server is already connected (`server` is only needed when several servers are connected). The Studio uses the saved server login ([connecting](../start/local-from-cloud.md#connecting)); no token is needed in the arguments and none appears in the answer; an address with a login or token is rejected. The project goes to the folder for cloud projects and stays linked to the server. The download runs in the background: the tool waits up to `wait_s` seconds (45 by default, at most 50: a larger `wait_s` is cut down, or the MCP client would drop the call on its own timeout), and if that is not enough, calling it again with the same arguments picks up the same download. A project already on the computer is not downloaded again.
- **`list_project_fields`** shows the project fields from the template description, the same ones as in the project settings: key, label, current value, allowed values (`options`) or a hint (`hint`, `example`), whether it is required (`required_at`: `create` at creation, `finalize` for submission) and the documents that print the field (`printed_in`, from the template sources). `set_with` names the tool that changes the field. In a team project author fields carry `author_values` by `slug`. `unknown_meta` lists metadata keys the template does not describe or print (for example a group written to the metadata instead of the author card).
- **`set_project_meta`** sets fields (`entries`) and removes keys (`unset`): a removed field falls back to the template value. Example: `{"entries": {"year": "2027"}, "unset": ["udc"]}`. The rights are those of the project settings.
- **Template update** works like the “Update template” dialog in the project settings.
    - `template_update_status` shows the project template version and the available updates: class (`patch`, `minor`, `major`), what is new and what breaks, for example `2026.1.1` and the recommended `2026.1.2`.
    - `plan_template_update` with `to_version` shows what happens to each file (`update`, `add`, `delete`, `merge`, `conflict`), which template signature places move to the new version (`signature_presets`: `updated`, and `kept` with the reason `manual`, `route` or `signed`), and returns a `fingerprint`. Project files are not changed.
    - `apply_template_update` with `to_version` and `fingerprint` applies exactly that plan; if the project changed meanwhile, make a new plan. `resolutions` decides conflicts (`{"path": "mine" | "theirs" | "markers"}`); by default your file is kept. The Studio takes a history snapshot first; the update can be undone in the project settings.
    - Planning and applying need the right to manage the project template (the owner) and a writable project. In the cloud, applying is audited (`project.template_update`).

### Syncing with a git remote

**`git_sync`** does what the project sync button does: saves a snapshot, takes others' changes and sends yours. In the local Studio it syncs with the cloud server (a project from the cloud) or with a connected repository; in the cloud, with a connected repository. The tool waits up to `wait_s` seconds (45 by default, at most 50: a larger `wait_s` is cut down, or the MCP client would drop the call on its own timeout) for the result; if that is not enough, the answer is `status: running` with the `operation_id`, and calling it again joins the same sync, just like pressing the button while a sync runs. Start a long sync with `wait_s: 0` or a short wait and call again. The answer has the `outcome` (`up_to_date`, `pushed`, `fast_forwarded`, `merged`, `conflicts`), how many versions were received and sent, and the files merged automatically. On conflicts nothing is sent and files on disk do not change: the answer lists the conflicting files, and you resolve them in the Studio with the “Resolve” button. The repository address and its credentials never appear in the answer. The rights are the button's: the editor role, and in a team project the right to edit the whole project. The tool is dangerous, so it is off by default.

### Documents: variant

- **`set_document_variant`** picks a document variant, like the “Document formats” switch in the project settings: for example `pptx`, `beamer` or `reveal` for the presentation. Pass `doc_id` from `list_documents` and `variant`; without `variant` the tool only shows the current variant and the ones allowed for the project language. An unknown variant is rejected with the list of allowed ones. Switching resets the document status to draft; the files of the previous variant stay. The rights are those of the interface: writing to the document, and a writable project. In the cloud the switch goes to the audit as `document.variant_update`.

### Project access (cloud)

The same actions as the Access panel, with the same rights; the local Studio has none of these tools.

- **`list_project_access`** shows the owner, people and groups with their roles. Whoever manages invitations (the owner or an editor allowed to share) also sees pending invitations.
- **`invite_to_project`** invites by `email` with the role `reader`, `reviewer` or `editor` (not above your own). `persona` binds the person to a project role: a supervisor who reviews is `role: "reviewer"`, `persona: "supervisor"`. Access starts once the person accepts. If the server has no email set up, the answer has a `link`: send it yourself, as from the invite dialog in the interface. The link is single-use.
- **`revoke_project_invitation`** revokes a pending invitation by `invitation_id`; the link from the email stops working.
- **`remove_project_member`** removes a member's access (`member` like `user:<id>` from `list_project_access`); only the owner can do this.

Dangerous tools (deleting a project or a file, rewinding history, syncing with a git remote, signing a submission with `sign_submission`, sending for signing with `send_for_signing`) are off by default: the administrator (cloud) or you (local) turns them on one by one. `get_signature_plan` shows the signature plan and what is missing. For a document sent for signing the plan has `pinned` (the version for signing: `sha256` and `pinned_at`) and `working_differs` (the current build differs from it); signatures are counted on the version for signing. `sign_submission` signs your slots in the documents of a checkpoint with a key stored in the Studio: the token needs the separate signing right, a password-protected key is not used over MCP (sign in the interface), and passwords and keys never appear in the response. A document that is out on a signing route is never frozen by the tool and is signed only when it is your turn to sign; otherwise it is skipped with the reason “The document is on a signing route”.

### Checkpoint deadlines

A checkpoint's submission deadline ([Submission deadline](submit.md#deadline)) is set by a person or an agent; the template does not know it.

- **`list_submission_profiles`** returns for each checkpoint `deadline` (a moment with a time zone, Moscow time), `deadline_state` (`none`, `upcoming`, `soon`, `today`, `packaged`, `overdue`; `overdue` means the checkpoint package was not built by the deadline), `deadline_hint` (the template's hint on when the deadline usually falls) and `packaged_at` (the latest package build in time). `get_project` returns the deadlines of all checkpoints in `deadlines`.
- **`set_checkpoint_deadline`** sets or removes a deadline: `profile_id` from `list_submission_profiles` and `deadline` in ISO 8601 with a time zone, for example `YYYY-MM-DDT23:59:00+03:00`; `null` removes it. A deadline in the past can be set. The rights are those of the “Set deadline” button: owner and editor. The tool does not change the signing route deadline. The deadline is not a build input, so no `signing_note` is added to the answer. The change goes to the audit log (`project.deadline`).

### Signing route (cloud)

Only the server runs the [“Send for signing”](send-for-signing.md) route, so the local Studio has none of these tools. Over MCP you can read the progress of a route and send documents; approving, signing or returning for revision is done only on the signing page in the interface: that is a person's decision.

- **`get_signing_route`** shows the progress of the route of a submission checkpoint (`profile_id` from `list_submission_profiles`): status and phase, steps with people and their states, whose turn it is now (`waiting_for`), the deadline, the stop reason (`stop_reason`: the version for signing changed outside the route, signatures or the final PDF changed outside the route, a participant left, returned for revision; routes stopped by an earlier Studio version may still show “document rebuilt”), who stopped it and the latest events. Each document has `sent` (the version for signing: SHA-256, date, round) and `changed` (changed since sending), and the route has `changed_docs`. When there are changes, `changed_hint` says which documents changed and that a person sends the new version in the interface. For a stopped route `stop_text` explains what happened and what to do, including when the version for signing changed outside the route. Without `profile_id` it gives a summary of every route in the project. Available to whoever can see build results; the return comment is visible to those who manage the route and to its participants.
- **`list_signing_tasks`** shows your signing tasks across all projects: where your action is needed now (`approve`, `approve_and_sign`, `sign`), who asks, for which checkpoint and by what deadline. `signing_page` is the address of the signing page: open it in the Studio.
- **`send_for_signing`** sends the documents of a submission checkpoint (`profile_id`) for signing, like the “Send for signing” button. It takes the saved route of the checkpoint (a draft, a stopped, a returned or a cancelled one: then this is “Send again”), and if there is none, creates one from the previous route or the order in the template. The checks are those of the button: documents are built, every slot has a signer, your own signature is ready, and the documents did not change between the check and the sending. On top of that every signer must already be in the project: with a person who has not accepted the invitation yet, send the route from the interface. If something is in the way, the tool lists the blockers and sends nothing. If you are a signer of the first step, sending counts as your approval. The tool does not sign with a key: “Send and sign” stays in the interface. It needs a role that can build a submission package (owner, editor). The tool is dangerous, so it is off by default; sending is recorded in the audit log as `signing_route.send`. The tool does not send a running or completed route: it refuses with `new_version_in_ui`, nothing changes, and a completed route stays tracked. A new version resets other people's approvals, so it is a person's decision: the “Send new version” button on the “Signing” card.

Optional signatures ([Optional signatures and skipping](send-for-signing.md#optional)) are read-only over MCP. `get_signing_route` returns `optional` (optional at this checkpoint), `extra` (a slot beyond the checkpoint) and the `skipped` status on a document slot, the `skipped` state, `skipped_at` and `skippable` on a participant, and the `skip_hint` hint on the route when it is the turn of a person who can be skipped. `get_signature_plan` shows `optional` and `skipped` (`at`, `route_id`) on a slot and `optional_pending` on the plan; `package_project` lists unsigned optional slots as `optional_unsigned`. **You cannot skip a participant or mark a signature optional over MCP**, there are no tools for it: a skip cancels a signature requirement and writes to a person, and a mistake can be undone only by a new send, that is an extra round for people. It is the author's decision in the interface, like sending a new version.

Date marks ([Signing date](send-for-signing.md#dates)) are read-only over MCP. `get_signature_plan` returns `dates` for a document slot (page, format and `text`: what is printed now, `null` for an empty mark) and `signed_at` (`at` and `source`: `approval`, the approval date in the signing route, or `manual`, the day the author set); `list_signatures` shows the marks in the placements. **You cannot add, move or remove date marks or set a manual date over MCP**: there is no placement tool, and editing the marks on a document held by a route can reset electronic signatures and needs a person to confirm. Do it in the interface: on a document's “Signatures” tab or under “Where the signatures go” in the route editor.

The route from the template ([Route from the template](send-for-signing.md#preset)) is read-only over MCP. `get_signing_route` returns the route's `preset`: the template version, the template's steps as personas, the signatures beyond the checkpoint with their condition (`extra_slots`), the “optional” marks (`optional`), the signatures the template did not add because the condition is not met (`skipped_by_condition`), and how the route differs (`differs`: `order`, `slots`, `optional`); `null` when the template defines no route. When the route can be edited and differs, `preset_hint` says that the author can reset it to the template in the interface. A document slot has `added_by` (`pack`: added by the template, `author`: by the author) and `preset_optional`. `get_signature_plan` shows a slot's `place`: `pack` (the place from the template), `seed` (a place the Studio set from the template and you did not touch), `manual` (changed) or `none`. Places on the template lines ([Signature places on the template lines](send-for-signing.md#anchors)) are read-only too: `get_signature_plan` returns a slot's `place_source` (`anchor`: the template place is set on a line, `mm`: in mm, `null`: manual or no place; whether the place landed on a line shows in `anchor_missing` and in the place mark in `list_signatures`) and the `anchor_missing` hint when the built document has no line for the signature; `list_signatures` returns the whole template mark of a place, with the anchor and the build; `get_compile` and `list_compiles` return `signature_places_moved`, how many template places the build moved to the new layout, and `compile_document` says so in a line of its reply; in `plan_template_update` an item with `after_build: true` lands on the template lines after a build. `list_submission_profiles` returns a checkpoint's `route_preset` with `signing_slots` and whether their condition is met by the project's people (`met`). **Resetting the route or a place to the template over MCP is not possible**: it edits the route and the places, which is done in the interface. `send_for_signing` applies the template to a new route just like the button.

You can edit and build documents out for signing through MCP: the route signs the version taken at sending, and edits do not reach it. If an editing or build tool touches a document of a running route, the answer gets a `signing_note`: which document is out for signing, that the changes will not reach the version for signing, and that a person sends the new version in the interface. This applies to `edit_tex`, `write_file`, `move_file`, `delete_file`, `compile_document`, `set_document_variant`, `set_project_meta`, `set_project_people`, `set_language`, `apply_template_update`, `vcs_restore` and `git_sync`. A shared file, project fields, a template update, a history restore and a sync touch every document out for signing. It is not a refusal; the action is done. `package_project` builds such documents from the version for signing and returns the `changed_after_sent` warning if the current build is newer.

### Template Studio (packs)

The **Template Studio** group works with [packs](../reference/pack.md) in Template Studio: spaces, files, checks, preview, a copy of a version and sending for review. A client sees these tools only when the section is on and you have access to Template Studio (an administrator grants it, "Who can edit templates"); in the cloud the token also needs the **Template Studio** scope. The rights are the same as in the section: your own workspaces only, released versions are read-only.

- **`pack_list_workspaces`** lists your workspaces; the other tools need their `id`. A version is named `<pack>/<template>/<version>` by folder names, for example `hse-cs-sse/coursework/2026.1.7`.
- **`pack_read`** without `version` shows the tree (packs, templates, versions with their status, `released` for released ones); with `version` it shows the version model: documents, questionnaire fields, signature slots, submission points, forms, example data sets, files and the `preview` block: what `pack_preview_build` can build (documents, `combination` switches with their allowed values, data sets, defaults, and in `author` how many authors each `staffing` gives and which documents are personal).
- **`pack_read_file`** and **`pack_write_file`** read and write a whole file. `if_match` (the etag from reading) protects against someone else's edit. Writing to a released version answers `version_released`: create a new version first.
- **`pack_scaffold_options`**, **`pack_create`** and **`pack_new_template`** create a pack with its first template or a template in an existing pack, like the New pack and New template dialogs: without `copy_from` the Minimal starting point (a GOST 7.32 report, two questionnaire fields, the author signature, one submission point), with `copy_from` a copy of the chosen version with new ids. `pack_scaffold_options` lists what can be copied and the taken ids.
- **`pack_lint`** checks a version or a manifest: findings with a file and a line. **`pack_classify`** shows the draft class (patch, minor, major) with its reasons and whether the number fits.
- **`pack_preview_build`** builds a version document on test data on a runner (no local TeX needed) and waits up to `wait_s` seconds (45 by default, at most 50: a larger `wait_s` is cut down, or the MCP client would drop the call on its own timeout). Start a long build with `wait_s: 0` or a short wait, then call again with `build_id`: the tool waits for the build already started and does not start a new one. `example` and `combination` pick the data set and the combination (language, staffing, supervisor, fields). In a team combination (`staffing` `team2`, `team3`) a personal document has an instance per author: `author` picks whose one to build, by the author's number from 1 (`"2"`) or by a slug from `authors` of a reply; without `author` the first author's document is built. A shared team document does not depend on `author`, and an author outside the combination is rejected with `preview_invalid`. The reply carries `author` (whose document was built) and `authors` (the authors of the combination: number, slug, name). `cancel: true` with `build_id` stops a build. **`pack_preview_read`** returns the PDF text or the build log.
- **`pack_outcome_inputs`** shows the version inputs for `pack_outcome`: ids (`lang`, `kind`, `staffing`, `supervisor`, `co_supervisor`, `academic_supervisor`, `nda`, `meta.<field>`, `answer.<form>.<field>`, `variant.<document>`), the allowed values, the default, the result sections an input changes (`affects`), the number of rules that read it (`rules`) and the example data sets. **`pack_outcome`** answers what a version produces for the given inputs, without building a PDF: the documents in the bundle with their final file names (a document that is off comes with its reason: the first unmet condition with the actual value), the participants, the submission point items, the route steps and the document and slot pairs, and warnings (for example, a step waits for a person who is absent). The `scenario` argument (the id of a `scenarios/<id>.yaml` file of the template) puts the scenario inputs and data set under `inputs`. The `inputs` go on top of the defaults and the scenario (`{"kind": "research", "meta.nda": true}`; `true` and `false` mean `yes` and `no`); an unknown input or a value outside the list answers `inputs_invalid` with `field`, `value` and `reason`. `state` picks what to read: `work_tree` (the working tree with unsaved edits, the default), `head` (the last commit) or `base` (the tip of the base branch); for a folder without git and for a new version `head` and `base` answer `diff_base_unavailable` with a `reason` and a hint. The default answer is compact text: a summary by section, the bundle, participants, submission points, routes and warnings. `include` picks the sections (`documents`, `meta`, `forms`, `participants`, `points`, `route`, `checks`, `branches` or `all`); `checks` and `branches` are calculated on request only. `trace: true` adds the decisions the shown elements refer to: the rule (a manifest file and pointer, or a rule built into the engine), the condition, the actual values and the verdict. `detail: full` adds fields, languages, point item signatures, pair conditions and the check rules. `format` picks the answer shape: `text` (the default), `json` (the same sections as a structure) or `both`. Both tools only read: they write, build and send nothing. The rate is the same as for the Result screen: 20 calls a second per person (one counter shared with the interface); on `outcome_busy` retry after `retry_after_s`. **`pack_outcome_compare`** compares two outcomes without building a PDF: the sides `left` and `right` (each: `state`, `scenario`, `example`, `inputs`; what is not named comes from the top-level arguments of the same names) can be on one state (two scenarios, two sets of inputs) or on two (the working tree against `head` or `base`: "what did I change"). The answer: changes with the symbols `+`, `~`, `-` by section and the main reason of each from the trace (the rule with a file and a pointer, the verdict on the left and on the right, the actual values); `detail: full` shows all reasons and all changes, `sections` keeps the sections you need, `format` picks text, structure or both. **`pack_outcome_impact`** answers "the outcome changes in N of M scenarios": it calculates the template scenarios on `base` (or `head`) and in the working tree, each has the status `changed`, `unchanged` or `error` (the scenario cannot be read on one of the sides) and the changes with symbols; `include_atlas: true` adds how many atlas rows change (off by default: it takes seconds on a thesis template). Without a base (`no_git`, `no_base`, `new_version`) both tools answer `diff_base_unavailable` with a hint. Read only; `compare` has the same rate as `pack_outcome` (20 per second), `impact` at most 6 times per minute per person.
- **`pack_outcome_lint`** runs the outcome linter of a version: slots outside every route, steps without a person, `visible_if` and `when` that will not hold, required hidden fields, missing translations and more (with `jinja: true` on the working tree also Jinja templates that fail to render). A finding has a file, a path, a line, a hint and an input combination; plus the rule coverage by the scenarios and the combinations worth closing with new ones. By default findings use the same words as the Check tab of the interface: a title, "How to fix", "This happens in n of m combinations", and the rule number, file and line in square brackets; `wording: tech` returns the linter rule texts. `severity` (`error`, `warning`, `info`), `limit`, `state`, `wording`, `format`. Read-only, 6 requests a minute ([details](../pack-studio/index.md#outcome-lint)).
- **`pack_set_placement`** sets signature places and date marks in `version.yaml`, like the visual place editor. With `build_id` the reply lists the anchors of the build: `sign_anchors` and `date_anchors` (ids as in the template) and `anchor_views`, the same anchors in plain terms: the slot `slot`, the date part `part`, and for a team author's line `author__<slug>` also the slug `author` and the author's name `author_name` from the data set of the build. **`pack_signature_render`** returns a picture of the preview build's PDF pages with the place boxes on top (blue signatures, red ones with errors, green date marks, orange dashes for anchor lines, purple suggested boxes), **`pack_signature_check`** checks the places automatically and suggests ready operations for `pack_set_placement` (the order is below).
- **`pack_new_version`**, **`pack_version_notes`** and **`pack_release`** are the steps of the New version wizard: a copy of the base as a draft, the `changes` notes in ru and en, the release with the registry entry. `pack_new_version` with `dry_run: true` creates nothing and shows the template versions, the default base and the numbers by class. **`pack_version_number`** changes the number of a draft (`action: renumber`, `to` or `update_class`) or moves edits made in a released version outside the Studio into a new version (`action: move_edits`), like "Change number" and "Move edits to a new version".
- **`pack_git_status`** shows the work branch, the edits, the PR and, with `checks: true`, the hosting checks status. **`pack_propose`** (Send for review) commits, checks, pushes and opens a PR with the workspace access. The tool is dangerous and off by default; without `confirm: true` it sends nothing and only returns a summary worth showing to the person.
- **`pack_help`** says which tool does what you need: all `pack_*` tools by task and the order "create a template and a branch, edit, check, propose". Start with it when unsure. The tools below cover everything in the Template Studio section and answer with compact text or structure (`format`: `text`, `json`, `both`). Refusals carry `code`, `detail` and `hint`: what to do next.
- **Workspaces.** **`pack_list_credentials`** lists saved git access (id, kind, host, status; no secrets). **`pack_workspace_create`** creates a workspace over a repository (`url` and the `credential_id` of a saved access; a public repository needs none) or over a folder (`kind: folder`, local only); the clone runs in the background, state `cloning`, then `ready`. Tokens and passwords are never accepted through MCP, in arguments or replies: add new access in the interface (Settings, Git). **`pack_workspace_refresh`** is "Refresh base": a workspace without a work branch and without edits moves to the fresh base; with unsaved edits the files stay as they are and the workspace `error` carries the `refresh_dirty` code. **`pack_workspace_delete`** deletes a workspace: without `confirm: true` it only describes the consequences. **`pack_official`** and **`pack_official_open`** show and open the installation's official packs. **`pack_catalog`** connects a folder to this Studio's catalog (local only): `check`, `apply` and `disconnect` change the whole Studio's catalog, `apply` and `disconnect` need `confirm: true`.
- **Reading and editing.** **`pack_tree`** the file tree (versions with status, files with `read_only`). **`pack_model`** the version model with manifest etags; **`pack_hints`** and **`pack_doc_library`** editor hints and starter documents; **`pack_submission`** submission profiles, slots and signing routes: the text shows the declared route of every submission point (the order by steps, the signatures of the items, the extra slots with their `when` condition and the optional mark), and with `routes: true` also the route in a combination (the steps as people from the data set, who puts which signature, what a condition left out). **`pack_patch_yaml`** edits YAML by JSON Pointer (`set`, `remove`, `insert` with `-` for the end of a list, `move`): comments and formatting stay, `if_match` guards against someone else's edit (`stale_file`), version and document manifests go through the loader and schema checks (`model_invalid`, the file is unchanged). **`pack_submission_edit`** and **`pack_model_action`** (`rename_field`, `add_document`, `remove_document`, `add_translation`) edit the version forms. **`pack_move_file`** moves a file, **`pack_delete_file`** deletes a file or folder (needs `confirm: true`). **`pack_checks`** edits the check rules of a version as a form: without `file` and `config` it shows the `checks/*.yaml` files with rules by index and `checks_version`; `file` with `ops` (`set_header`, `add_rule`, `set_rule`, `remove_rule`, `move_rule`) edits a rules file, `config` writes `checks_version` (disabled categories and rules, `severity_override`). All edits or none, `if_match` by etag. A released version answers `version_released` with the hint `pack_new_version`.
- **Scenarios and outcome.** **`pack_scenario_list`**, **`pack_scenario_write`** (create or edit, `if_match` by etag, `record_snapshot` accepts the snapshot), **`pack_scenario_delete`** (soft, the reply carries the deleted body) and **`pack_scenario_run`** (statuses: matched, changed, error, unchecked, and rule coverage). **`pack_outcome_atlas`** shows which inputs change the outcome (dimensions, outcome count, groups; `pin`, `limit`), **`pack_outcome_explain`** answers "Why?" for an element (decision chain, "what if"), **`pack_outcome_matrix`** gives the scenario-by-section matrix. Rates: the run and `explain` like `pack_outcome` (20 a second), the atlas 6 a minute, the matrix 6 a minute.
- **Git step by step.** **`pack_git_branches`**, **`pack_git_branch`** (create or switch a branch; `from_base: true` creates a new branch from the fresh base branch, not from the current head: this is how the next piece of work starts after a merged PR, the tree must be clean or the answer is `workspace_dirty`, a taken name is rejected with `branch_exists`), **`pack_git_commit`** (as the person's profile), **`pack_git_diff`**, **`pack_git_checks`** (errors that stop a proposal, and hosting CI), **`pack_git_merge_base`** ("Update from base", a conflict cancels the merge) and **`pack_git_start_over`** ("Start over": without `confirm: true` it only describes what will be lost; with unsaved edits it also needs `discard: true`). A full agent cycle: `pack_git_branch`, edits, `pack_lint`, `pack_outcome` and scenarios, `pack_git_commit`, `pack_git_diff`, `pack_propose`.
- **Changes and the next step.** **`pack_changes`** answers what the Changes panel and the main button of the interface show: changed files and versions, errors and warnings of the changed places, whether notes are needed, the merge request and its checks, how far the main branch moved ahead, and `next_step` (the button label, its hint and the tools that do the step, for example "Describe changes" and `pack_version_notes`). `version` picks the open version, by default the newest changed one. Read-only.

A refusal comes as an error with a `code` from the Template Studio list, for example `version_released`, `stale_file` (with the current `etag`), `lint_failed` (with findings) or `fork_required`.

### Signature places by an agent

The agent places the pack's signatures itself and checks that every signature lands where it should. The person only looks at the result.

1. **`pack_preview_build`** builds the document for the situation you need (`scenario` or `combination`): places are computed for this build.
2. **`pack_signature_render`** with `build_id` sends a picture of the pages with places and signature lines. A multimodal model looks at it itself; the text of the answer is a legend in millimetres: slot, page, box, where the place comes from (the document's own, the slot's shared one, an anchor).
3. **`pack_signature_check`** with the same `build_id` checks every place: whether there is a box, on the right page, not off the sheet and not closer than 5 mm to the edge, not covering text (the "(signature)" caption and underscores are fine), not overlapping other boxes and date marks, no drawing or table under it (the share of dark pixels), and whether it sits on its own signature line. The own line is the slot's anchor from the template (`\hseSignAnchor`), otherwise a rule or a run of underscores next to the slot's label ("Supervisor ____"). Findings have a text and numbers; bad places get a suggested box over the middle of the line and `suggested_ops`: `bind_anchor` when the slot has an anchor (the place survives text edits), otherwise `set_place` with a box in millimetres.
4. **`pack_set_placement`** with `build_id` applies `suggested_ops` or your own decision.
5. **`pack_signature_render`** and **`pack_signature_check`** again: no rebuild is needed, places are not part of the preview build. Rebuild only after editing the template text.

The check sees only what is in the PDF: text, lines, pixels. It still looks at a slot that this situation does not need (for example, there is no co-supervisor); build the preview for a situation where it exists.

### Builds

**`compile_document`** starts a build, like the “Build” button. By default (`wait: true`) the tool waits up to 45 seconds for the result, which is less than MCP clients wait for an answer. If the build takes longer (for example, a cloud build on a personal runner), the answer is not an error: `status: in_progress` and the `compile_id`, and the build keeps running. With `wait: false` the tool returns the `compile_id` at once. `get_compile` with that `compile_id` shows the result; `cancel_compile` stops the build.

## Security

- The client acts as the token owner: the same project roles, quotas and limits as in the interface. Other people's projects do not exist for it.
- An MCP token needs only the **MCP** permission and gives no access to the regular API. Revoke it where it was issued; it stops working at once. Its permissions are changed in the same place ([Token permissions](#scopes)) and also apply at once.
- Browser cookies are not accepted on `/mcp`.
- Every call is logged: tool, project, outcome and time, without argument values. In the cloud the log is on **Admin → MCP server** and in the general audit log; locally it is in the MCP settings.
- Calls are rate limited (120 a minute per person by default); builds, file writes and git also count against their own limits.

## For administrators

On **Admin → MCP server**:

- the MCP server master switch;
- tool groups and single tools with switches; dangerous ones are enabled by name;
- the **Administration** group (users, queue, runners, audit, mail log) is off by default; even when on it is only available to an instance administrator whose token has the **MCP: administration** permission;
- the **Template Studio** group is visible only to people with access to Template Studio ("Who can edit templates");
- the call log.

**`admin_runner_fleet`**, **`admin_runner_fleet_upgrade`** and **`admin_runner_fleet_cancel`** do what the “Update all runners” window does after a Studio update ([Runners](../deploy/runners.md#runner-fleet-upgrade)). `admin_runner_fleet` lists the out-of-date instance runners: the kind (`docker`, `kubernetes`, `ssh` are updated from here, `manual` only by hand, with the reason in `manual_reason`), the version and how many builds are running on it (`running_jobs`); with `batch_id` it returns the progress and result of a run. `admin_runner_fleet_upgrade` starts the update of the given `runner_ids`, or of all that can be updated from here (`all: true`), and returns the run at once; runners are updated one at a time, a runner with a build in progress waits for it and is skipped (`busy`) if it does not free up within 15 minutes. The tool is dangerous: runners restart, so it is enabled by name. `admin_runner_fleet_cancel` stops a run after the current runner. Starting and stopping are written to the audit log (`runner_fleet.upgrade.start`, `finished`, `cancel`); reading is not.

**`admin_list_mail_log`** answers “did the email arrive” without opening **Admin → Mail**: mail log rows, newest first. Filters are `recipient` (exact address, case-insensitive), `template` (mail kind, such as `invite`), `status` (`sent`, `failed`, `not_sent`, `suppressed`) and `since` (an ISO 8601 date or moment, UTC when no time zone is given), at most 50 rows (`limit`, 20 by default). A row has the time, mail kind, address and subject, outcome, reason, SMTP reply code, who caused the email (`cause`: a person, a request without sign-in or a background task, and `actor_id`), the number of attempts (`attempts`), the time of the next automatic retry (`next_attempt_at`, empty when no more retries will happen), the time of the last attempt (`last_attempt_at`) and, for a manual resend, the id of the original email (`resent_from_id`); the recipient and the project appear only as ids. The response has no mail preview, names, links or failure text. The tool only reads, and reading is not audited.
