# AGENTS.md: blockchainlab-compose

Instructions for AI coding agents (Grok, Cursor, Claude Code, Codex, Copilot and others) working **in** this repo or **using it as a building block**. Humans: see [README.md](README.md).

## What this is

Idea-to-repo engine behind blockchainlab.com/forge: turns a plain-language token/NFT idea into a tested Foundry project (components from blockchainlab-index, pragma/licence checks, generated glue, tests, deploy script, CI) and optionally creates it under github.com/Blockchains.

- Kind: cli, github-action · stability: `beta` · licence: MIT
- Machine-readable manifest: [`blocks.json`](blocks.json) (schema: [BLOCKS-SCHEMA](https://github.com/Blockchains/.github/blob/main/docs/BLOCKS-SCHEMA.md))
- How it fits with the other Blockchains repos: [Build with Blocks](https://github.com/Blockchains/.github/blob/main/docs/BUILD-WITH-BLOCKS.md)

## Setup

```bash
pip --version   # engine is stdlib only
pip install jsonschema   # only for the tests (blocks.json schema validation)
foundryup        # forge on PATH
```

## Build and test

```bash
python3 -m unittest discover -s tests -v
python3 -m blcompose.compose "An NFT membership collection with ERC-2981 royalties, role-based minting, a pause switch, and a paid mint priced in USD using a Chainlink ETH/USD price feed" --name ci-nft --out /tmp/ci-nft --json nft.json
```

Tests hit **live** public networks/APIs (the org rule is no mocks). A failure can be an upstream outage: re-run before changing code.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `XAI_API_KEY` | no | one Grok review call written to REVIEW.md (not an audit) |
| `MAINNET_RPC_URL` | no | enables generated live-chain fork tests |
| `FORGE_TOKEN` | no | repo secret; needed by the Action to create repos |

## Structure

| Path | What |
|---|---|
| `blcompose/compose.py` | pipeline + CLI (`main`) |
| `blcompose/recipes.py` | capability → glue/test generators |
| `blcompose/agentdocs.py` | AGENTS.md / llms.txt / blocks.json for composed repos (parses src/*.sol) |
| `blcompose/blocks.schema.json` | vendored copy of the org blocks schema (a test checks it matches the published one) |
| `tests/test_engine.py, tests/test_agentdocs.py` | unit tests |
| `.github/workflows/compose.yml` | dispatchable Action used by blockchainlab.com |
| `.github/workflows/ci.yml` | re-composes both reference ideas + refusal check |

## Conventions

- Copied components stay unmodified with SPDX headers; NOTICE lists every file.
- GPL components are refused for now; source-available licences are never copied.
- Outputs are deterministic for the same index + idea.

## Extension points

- New capability: add a recipe in `blcompose/recipes.py`, the taxonomy id in blockchainlab-index `taxonomy/capabilities.json`, and a CI idea that exercises it.
- Generated agent docs: edit `blcompose/agentdocs.py`; `tests/test_agentdocs.py` validates the manifest against the schema and the real generated sources.

## Do

- Run without `--create` while developing; inspect `/tmp/<name>`.

## Don't

- Create repos from tests.
- Hand-edit composed reference repos (they must stay reproducible).
- Invent data, mock network responses in shipped code, or hard-code values that should come from the live source; every repo here is 'no mocks, real data'.
- Commit secrets, keys or `.env` files. Run `gitleaks` before pushing; CI and the org policy reject leaks.

## Using it from another project

- **python3 -m blcompose.compose** (cli): `python3 -m blcompose.compose "<idea>" --name <repo> [--out DIR] [--index PATH] [--json result.json] [--create --wait]`
- **Compose a project** (github-action): `workflow_dispatch inputs: idea, name, request_id → results/<request_id>.json`

See the README section [Use as a building block](README.md#use-as-a-building-block) for a copy-paste example.

## Related blocks

- [Blockchains/blockchainlab-index](https://github.com/Blockchains/blockchainlab-index): component source (catalog, components, taxonomy)
- [Blockchains/forge-dao-governance-token](https://github.com/Blockchains/forge-dao-governance-token): reference output, re-composed in CI
- [Blockchains/forge-usd-priced-membership-nft](https://github.com/Blockchains/forge-usd-priced-membership-nft): reference output, re-composed in CI
- [Blockchains/grokhack-forge](https://github.com/Blockchains/grokhack-forge): sister composer for Grok apps
- [Blockchains/blockchainlab-sdk](https://github.com/Blockchains/blockchainlab-sdk): add a data layer to a generated dApp
