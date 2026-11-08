---
title: AI clients (MCP)
description: Connect Claude, Cursor and other AI clients to the Studio over the Model Context Protocol, locally and in the cloud.
tags:
  - Workbench
  - AI agent
---

# AI clients (MCP)

<p class="hds-lede">The Studio can act as a Model Context Protocol server. An external AI client (Claude Desktop, Claude Code, Cursor, VS Code, Zed) sees your projects and works in them with the Studio's tools: it reads and edits files, builds PDFs, goes through findings and saves snapshots. It acts on your behalf and can do no more than you can.</p>

## Turn it on

=== "Local Studio"

    **Settings → AI clients (MCP) → “Enable the MCP server”**. The server address is `http://127.0.0.1:17240/mcp`, the Studio's own port. No token is needed: the server only answers programs on this computer and rejects requests whose `Host` or `Origin` names another site.

=== "Cloud Studio"

    An administrator turns MCP on: **Admin → MCP server → “Enable the MCP server”**. Then everyone issues a token: **Settings → Account → Tokens → New token**, permission **MCP**. The server address is `https://<Studio address>/mcp`; the token goes in the `Authorization: Bearer <token>` header.

## Connect a client

Ready-made configs with your address are in the Studio: **Settings → AI clients (MCP)**.

=== "Claude Code"

    ```bash
    # local
    claude mcp add --transport http hse-doc-studio http://127.0.0.1:17240/mcp
    # cloud
    claude mcp add --transport http hse-doc-studio https://studio.example.org/mcp \
      --header "Authorization: Bearer hsd_pat_..."
    ```

=== "Cursor, VS Code"

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

    VS Code uses the top-level key `servers` and `"type": "http"`. A local Studio needs no `headers`.

=== "Claude Desktop and others (stdio)"

    Clients that launch the server as a process use the `hse-doc-studio mcp` bridge, which forwards requests to a running Studio.

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

    Without `--url` the bridge connects to the local Studio, which must be running.

## What is available

- **Tools.** Projects (list, card, create, metadata, supervisor and authors), files (tree, read, search, edit, write, move), builds (run and wait for the result, history, log, cancel), checks and the normcontrol report, requirements, review comments (cloud), history and git sync, submission profiles and packages, signature status. Project tools take `project_id`; start with `list_projects`.
- **Resources.** `studio://projects`, the project card `studio://projects/<id>`, files `studio://projects/<id>/files/<path>` and build PDFs.
- **Prompts.** `fix_build`, `normcontrol` (go through findings), `review_changes` (describe changes before a snapshot).

### Projects: creation, people, a project from the cloud

- **`create_project`** creates a project from a template (`pack_id`, `template_id`, `version` from `list_templates`). The local Studio needs `folder`, the full path to a new folder. In the cloud the server picks the folder: the schema has no `folder` field, and a value sent anyway is not used.
- **`set_project_people`** changes the supervisor (`supervisor`), co-supervisor (`co_supervisor`), academic programme supervisor (`academic_supervisor`) and authors, which go to the title page, the application and the statement. The rights are those of the project settings: a role that may change settings, and a project that is writable. The values reach the PDF on the next build: `common/meta.tex` is regenerated before every build.
    - A supervisor has `name`, `title` (position), `degree` (academic degree or rank) and `role` (`university` or `company`). Fields you pass replace the current ones, the rest stay; an empty string clears the position or degree, an empty `name` removes the person from the project.
    - `author` changes one author and leaves the others alone: `name`, `group`, `email`; an empty string clears the group or e-mail. In a team project the author is picked by `slug` from `get_project`, in a solo project the first author changes.
    - `authors` replaces the whole list: `name`, `group` and `email` of each author, the first one goes to the title page. To keep the topic and file set of existing authors in a team project, pass their `slug` from `get_project`.
    - `clear: ["co_supervisor"]` removes the co-supervisor (`supervisor` and `academic_supervisor` work the same way).
    - Example: `{"supervisor": {"name": "S. A. Shershakov", "degree": "PhD"}, "author": {"group": "MPI251", "email": "ivanov@edu.hse.ru"}}`.
    - Every change is audited: in the cloud as a `project.people_update` event with the old and new values; locally the call is in the MCP log.
- **`clone_cloud_project`** (local Studio only) downloads a project from a cloud Studio, like the “Open” button of a cloud project in the list. Pass the project `url`, such as `https://studio.example.org/projects/<id>/`, or `project_id` if the server is already connected (`server` is only needed when several servers are connected). The Studio uses the saved server login ([connecting](../start/local-from-cloud.md#connecting)); no token is needed in the arguments and none appears in the answer; an address with a login or token is rejected. The project goes to the folder for cloud projects and stays linked to the server. The download runs in the background: the tool waits up to `wait_s` seconds (45 by default, less than MCP clients wait), and if that is not enough, calling it again with the same arguments picks up the same download. A project already on the computer is not downloaded again.
- **`list_project_fields`** shows the project fields from the template description, the same ones as in the project settings: key, label, current value, allowed values (`options`) or a hint (`hint`, `example`), whether it is required (`required_at`: `create` at creation, `finalize` for submission) and the documents that print the field (`printed_in`, from the template sources). `set_with` names the tool that changes the field. In a team project author fields carry `author_values` by `slug`. `unknown_meta` lists metadata keys the template does not describe or print (for example a group written to the metadata instead of the author card).
- **`set_project_meta`** sets fields (`entries`) and removes keys (`unset`): a removed field falls back to the template value. Example: `{"entries": {"year": "2027"}, "unset": ["udc"]}`. The rights are those of the project settings.

### Syncing with a git remote

**`git_sync`** does what the project sync button does: saves a snapshot, takes others' changes and sends yours. In the local Studio it syncs with the cloud server (a project from the cloud) or with a connected repository; in the cloud, with a connected repository. The tool waits up to `wait_s` seconds (45 by default) for the result; if that is not enough, the answer is `status: running`, and calling it again joins the same sync, just like pressing the button while a sync runs. The answer has the `outcome` (`up_to_date`, `pushed`, `fast_forwarded`, `merged`, `conflicts`), how many versions were received and sent, and the files merged automatically. On conflicts nothing is sent and files on disk do not change: the answer lists the conflicting files, and you resolve them in the Studio with the “Resolve” button. The repository address and its credentials never appear in the answer. The rights are the button's: the editor role, and in a team project the right to edit the whole project. The tool is dangerous, so it is off by default.

Dangerous tools (deleting a project or a file, rewinding history, syncing with a git remote) are off by default: the administrator (cloud) or you (local) turns them on one by one. Signing documents with an electronic signature is not available over MCP.

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
- the **Administration** group (users, queue, runners, audit) is off by default; even when on it is only available to an instance administrator whose token has the **MCP: administration** permission;
- the call log.
