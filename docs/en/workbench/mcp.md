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

- **Tools.** Projects (list, card, create, metadata, supervisor and authors, template update, access and invitations in the cloud), files (tree, read, search, edit, write, move), builds (run and wait for the result, history, log, cancel), checks and the normcontrol report, requirements, review comments (cloud), history and git sync, submission profiles and packages, signature status, the signing route (cloud). Project tools take `project_id`; start with `list_projects`.
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
- **`clone_cloud_project`** (local Studio only) downloads a project from a cloud Studio, like the “Open” button of a cloud project in the list. Pass the project `url`, such as `https://studio.example.org/projects/<id>/`, or `project_id` if the server is already connected (`server` is only needed when several servers are connected). The Studio uses the saved server login ([connecting](../start/local-from-cloud.md#connecting)); no token is needed in the arguments and none appears in the answer; an address with a login or token is rejected. The project goes to the folder for cloud projects and stays linked to the server. The download runs in the background: the tool waits up to `wait_s` seconds (45 by default, less than MCP clients wait), and if that is not enough, calling it again with the same arguments picks up the same download. A project already on the computer is not downloaded again.
- **`list_project_fields`** shows the project fields from the template description, the same ones as in the project settings: key, label, current value, allowed values (`options`) or a hint (`hint`, `example`), whether it is required (`required_at`: `create` at creation, `finalize` for submission) and the documents that print the field (`printed_in`, from the template sources). `set_with` names the tool that changes the field. In a team project author fields carry `author_values` by `slug`. `unknown_meta` lists metadata keys the template does not describe or print (for example a group written to the metadata instead of the author card).
- **`set_project_meta`** sets fields (`entries`) and removes keys (`unset`): a removed field falls back to the template value. Example: `{"entries": {"year": "2027"}, "unset": ["udc"]}`. The rights are those of the project settings.
- **Template update** works like the “Update template” dialog in the project settings.
    - `template_update_status` shows the project template version and the available updates: class (`patch`, `minor`, `major`), what is new and what breaks, for example `2026.1.1` and the recommended `2026.1.2`.
    - `plan_template_update` with `to_version` shows what happens to each file (`update`, `add`, `delete`, `merge`, `conflict`), which template signature places move to the new version (`signature_presets`: `updated`, and `kept` with the reason `manual`, `route` or `signed`), and returns a `fingerprint`. Project files are not changed.
    - `apply_template_update` with `to_version` and `fingerprint` applies exactly that plan; if the project changed meanwhile, make a new plan. `resolutions` decides conflicts (`{"path": "mine" | "theirs" | "markers"}`); by default your file is kept. The Studio takes a history snapshot first; the update can be undone in the project settings.
    - Planning and applying need the right to manage the project template (the owner) and a writable project. In the cloud, applying is audited (`project.template_update`).

### Syncing with a git remote

**`git_sync`** does what the project sync button does: saves a snapshot, takes others' changes and sends yours. In the local Studio it syncs with the cloud server (a project from the cloud) or with a connected repository; in the cloud, with a connected repository. The tool waits up to `wait_s` seconds (45 by default) for the result; if that is not enough, the answer is `status: running`, and calling it again joins the same sync, just like pressing the button while a sync runs. The answer has the `outcome` (`up_to_date`, `pushed`, `fast_forwarded`, `merged`, `conflicts`), how many versions were received and sent, and the files merged automatically. On conflicts nothing is sent and files on disk do not change: the answer lists the conflicting files, and you resolve them in the Studio with the “Resolve” button. The repository address and its credentials never appear in the answer. The rights are the button's: the editor role, and in a team project the right to edit the whole project. The tool is dangerous, so it is off by default.

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

### Builds

**`compile_document`** starts a build, like the “Build” button. By default (`wait: true`) the tool waits up to 45 seconds for the result, which is less than MCP clients wait for an answer. If the build takes longer (for example, a cloud build on a personal runner), the answer is not an error: `status: in_progress` and the `compile_id`, and the build keeps running. With `wait: false` the tool returns the `compile_id` at once. `get_compile` with that `compile_id` shows the result; `cancel_compile` stops the build.

## Security

- The client acts as the token owner: the same project roles, quotas and limits as in the interface. Other people's projects do not exist for it.
- An MCP token needs only the **MCP** permission and gives no access to the regular API. Revoke it where it was issued; it stops working at once.
- Browser cookies are not accepted on `/mcp`.
- Every call is logged: tool, project, outcome and time, without argument values. In the cloud the log is on **Admin → MCP server** and in the general audit log; locally it is in the MCP settings.
- Calls are rate limited (120 a minute per person by default); builds, file writes and git also count against their own limits.

## For administrators

On **Admin → MCP server**:

- the MCP server master switch;
- tool groups and single tools with switches; dangerous ones are enabled by name;
- the **Administration** group (users, queue, runners, audit, mail log) is off by default; even when on it is only available to an instance administrator whose token has the **MCP: administration** permission;
- the call log.

**`admin_list_mail_log`** answers “did the email arrive” without opening **Admin → Mail**: mail log rows, newest first. Filters are `recipient` (exact address, case-insensitive), `template` (mail kind, such as `invite`), `status` (`sent`, `failed`, `not_sent`, `suppressed`) and `since` (an ISO 8601 date or moment, UTC when no time zone is given), at most 50 rows (`limit`, 20 by default). A row has the time, mail kind, address and subject, outcome, reason, SMTP reply code, who caused the email (`cause`: a person, a request without sign-in or a background task, and `actor_id`), the number of attempts (`attempts`), the time of the next automatic retry (`next_attempt_at`, empty when no more retries will happen), the time of the last attempt (`last_attempt_at`) and, for a manual resend, the id of the original email (`resent_from_id`); the recipient and the project appear only as ids. The response has no mail preview, names, links or failure text. The tool only reads, and reading is not audited.
