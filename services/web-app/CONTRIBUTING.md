# Contributing to hse-doc-studio Web

## Setup

```bash
make install
make dev
```

## Code Style

ESLint + Prettier; TypeScript strict mode.

```bash
make fmt
make lint
make typecheck
```

## Architecture

Feature-Sliced Design — `app → pages → widgets → features → entities → shared`. Dependencies only point downward. Each slice exposes a public API via `index.ts`.
