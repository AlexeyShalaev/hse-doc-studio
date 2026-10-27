# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a vulnerability

**Please do not report security vulnerabilities via public GitHub Issues.**

Send a report to **shalaevad.alexey@gmail.com** with:

- Description of the vulnerability
- Steps to reproduce
- Potential impact and affected versions

We aim to acknowledge reports within **48 hours** and provide a fix within **7 days**
for critical issues.

Once the fix is released, we will credit you in the release notes unless you prefer
to remain anonymous.

## Threat model: Git synchronization

Git synchronization is optional and off until a user connects a remote repository to a project. Without a remote the Studio makes no git network requests.

What the Studio protects and what it does not:

- **Tokens and SSH private keys** are stored encrypted (Fernet, key in `secrets/master.keys.json` with mode 0600, or supplied through `HSE_STUDIO__SECRETS__KEY` / `HSE_STUDIO__SECRETS__KEY_FILE`). This defends against accidental leaks: a copied data directory without the key, a cloud-drive snapshot, a screenshot, a log. It does **not** defend against malware running as the same user, or against someone who holds the whole data directory together with the key. If the data directory lives in a synced folder, move the key file out of it.
- **A token never appears in process arguments, logs, the store config or API responses.** It is passed to a single `git` process through the environment as an `http.<url>.extraheader` bound to that scheme, host and port, so a redirect or an edited remote URL cannot send it to another host. A credential is only used for the host it was created for.
- **Git is run in a hardened mode.** The environment is an allow-list, hooks are disabled (`core.hooksPath` points at an empty directory), `core.fsmonitor`, `credential.helper` and `core.sshCommand` are cleared, and only the transports a given remote needs are allowed. User git configuration, `~/.ssh`, `ssh-agent` and credential helpers are not read. A project store whose config contains settings the Studio did not write is refused (`store_untrusted`), so a hostile copied folder cannot execute code through git config.
- **The server is authenticated, never trusted blindly.** TLS verification cannot be switched off. For servers with a private CA the user may trust a PEM certificate for that one server, or pin the server certificate fingerprint after confirming it, as with SSH host keys. SSH uses the Studio's own `known_hosts` with `StrictHostKeyChecking=yes`; a changed host key stops the connection and is replaced only after the user types the host name. Plain `http` is refused unless the operator enables `HSE_STUDIO__GIT__ALLOW_INSECURE_HTTP` and the remote opts in.
- **The remote is untrusted input.** Incoming trees are checked before anything is written: paths with `..`, absolute paths, `.git/`, the Studio's private directories, symlinks and submodules are skipped; the schema version of the remote project is checked first; merges never leave conflict markers in files, never force-push, and keep a pre-merge snapshot so the user can go back. Bundle files are verified with `git bundle verify` and, if encrypted, authenticated per frame so truncated or reordered files are rejected.
- **What leaves the machine is the project history**: sources, form answers, signature images and files marked NDA. The Studio asks the user to confirm that the repository is private for NDA projects and warns before building such a project in third-party CI. Settings export and import never carry git tokens, SSH keys, the encryption key, trusted hosts or the author profile.
- **Out of scope:** a compromised hosting service that serves malicious but well-formed content is limited to what a collaborator could write; a user who deliberately publishes to a public repository; protecting secrets from other local users when the operating system cannot enforce file permissions (the Studio then says so in Settings).

Report issues in this area through the private channel above, not in public issues.
