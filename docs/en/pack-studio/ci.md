---
title: Command line and CI
description: Template Studio on your computer, the hse-doc-studio pack command for checks without the interface and CI for your packs repository.
tags:
  - Templates
  - Pack authors
---

# Command line and CI

<p class="hds-lede">The checks of Template Studio are on the command line too: `hse-doc-studio pack`. The CI of a packs repository runs it, and an agent in the repository can use it. The whole Template Studio runs on your computer with one command.</p>

## Running it locally

- **Pack author:** the "Template Studio only" profile in Docker, without sign-in or projects: [Template Studio on your computer](../deploy/pack-studio-local.md).
- **Studio developer:** `make pack-studio` in a repository checkout, at <http://localhost:3001/pack-studio>, with a workspace over the checkout's `packs/`.
- **Your local Studio:** turn the section on in **Settings** and open the packs folder as a workspace.

## The `hse-doc-studio pack` command

It works on a packs folder without the Studio and without TeX: `pack lint`, `pack check`, `pack classify`, `pack new-version`, `pack freeze`. All commands, options and exit codes: [Packs and templates, the command](../reference/pack.md#pack-cli).

Without a Python install the command is in the Studio image:

```bash
docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/alexeyshalaev/hse-doc-studio:<version> \
  hse-doc-studio pack check packs
```

## CI for your packs repository { #ci }

The check for every PR is `hse-doc-studio pack check <packs folder> --base <base branch>`: the linter, immutability of released versions, manifest schemas, the class of unreleased versions. With `--base` the released versions are those in `releases.yaml` of the base branch: a PR can neither remove nor recompute their entries. Run it in the Studio image of the version your authors use. No TeX and no secrets are needed.

`hse-doc-studio pack ci init` in the root of the packs repository puts a ready CI file there: `--provider github` (default) writes `.github/workflows/hse-packs.yml`, `--provider gitlab` writes `.gitlab-ci.yml`. The job runs `pack check` in the Studio image of the same version as the command, against the base branch on PRs and MRs. Options and details: [Packs and templates, CI for a packs repository](../reference/pack.md#pack-ci). After a Studio update run the command again with `--force` so that CI takes the new image.

Template Studio shows the hosting check status in the git panel, see [Propose changes](propose.md#hosting-checks).

<!-- T16 (MCP): an "AI agents (MCP)" section here: the pack_* tools, the "Template author" right, the packs PAT scope. -->
