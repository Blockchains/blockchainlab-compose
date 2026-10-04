# blockchainlab-compose

[![CI](https://github.com/Blockchains/blockchainlab-compose/actions/workflows/ci.yml/badge.svg)](https://github.com/Blockchains/blockchainlab-compose/actions/workflows/ci.yml)

The engine behind **[blockchainlab.com /forge](https://blockchainlab.com/forge)**. Describe a project in plain language; it picks components from
the Blockchains forks, checks they fit together, writes the glue code, tests, deploy script and CI, creates the repo under
[github.com/Blockchains](https://github.com/Blockchains), waits for CI and returns the link.

```
idea ─► capabilities: blockchainlab-index taxonomy matcher (+ optional bge-small semantic match) + deterministic keyword rules
     ─► archetype (token | nft)                       unsupported capability → exit 3 with the list of what is supported
                                                       (embedding-only matches for unsupported capabilities are reported as ignored, not fatal)
     ─► components: exact files the glue imports, each looked up in blockchainlab-index (licence, pragma, pinned commit)
     ─► fetch: files + full import closure copied unmodified from the Blockchains forks at pinned release tags (NOTICE written)
     ─► compatibility: every pragma must accept solc 0.8.30; every SPDX id must be OSI; project licence verdict (GPL → refused for now)
     ─► generate: glue contracts, Foundry tests (unit + live-chain fork test when MAINNET_RPC_URL is set), Deploy.s.sol, CI, Sepolia deploy workflow, README
     ─► optional Grok review (XAI_API_KEY in env: one grok-4.7 call, fallback grok-4.5 → REVIEW.md, labelled not-an-audit; 403 → 'xAI credits needed'; no key → skipped)
     ─► forge build + forge test locally ─► gitleaks ─► gh repo create Blockchains/<name> --push ─► wait for CI ─► JSON result with links
```

| Capability (taxonomy id) | What gets generated |
|---|---|
| `fungible-token` | ERC-20 with hard cap, mint guarded by role/owner |
| `token-permit` | EIP-2612 permit (+ signature test incl. replay) |
| `governance` | ERC20Votes + Governor (settings, simple counting, 4% quorum) + TimelockController; test runs a full propose → vote → queue → execute |
| `nft` | ERC-721 with max supply, base URI |
| `royalties` | ERC-2981 default royalty |
| `price-oracle` | Chainlink `AggregatorV3Interface` USD pricing with staleness check, refunds, withdraw; live ETH/USD fork test |
| `pausable` | ERC20Pausable / ERC721Pausable |
| `access-control` | AccessControl roles (otherwise Ownable) |

## Use
```bash
python3 -m blcompose.compose "An NFT membership collection with royalties, role-based minting and a USD price via Chainlink" --name my-club            # generate + test in /tmp/blcompose/my-club
python3 -m blcompose.compose "..." --name my-club --create --wait --json result.json                                                                  # + create Blockchains/my-club, push, wait for CI
```
Needs Python 3.10+, `forge`, `git`, and (for `--create`) `gh` authenticated as Blockchains. The index is cloned from
[blockchainlab-index](https://github.com/Blockchains/blockchainlab-index) unless `--index PATH` is given.

**As an Action:** run the **Compose a project** workflow (`idea`, `name`, `request_id`). blockchainlab.com dispatches it and reads
`results/<request_id>.json`. Creating repos needs a `FORGE_TOKEN` secret (fine-grained PAT owned by Blockchains); without it the workflow stops with a clear error.

## Composed with this engine (no hand edits, CI green)
- [Blockchains/forge-dao-governance-token](https://github.com/Blockchains/forge-dao-governance-token)
- [Blockchains/forge-usd-priced-membership-nft](https://github.com/Blockchains/forge-usd-priced-membership-nft)

CI here re-composes both ideas from the live index on every push, runs their tests, and checks an unsupported idea is refused.

MIT licence. Generated projects are MIT; copied components keep their own licences (see each project's NOTICE).

<!-- blocks:start -->
## Use as a building block

> **For AI agents and builders:** read [`AGENTS.md`](AGENTS.md) (setup, commands, structure, rules), [`llms.txt`](llms.txt) (doc map) and the machine-readable [`blocks.json`](blocks.json) ([schema](https://github.com/Blockchains/.github/blob/main/docs/BLOCKS-SCHEMA.md)). How all Blockchains blocks fit together: **[Build with Blocks](https://github.com/Blockchains/.github/blob/main/docs/BUILD-WITH-BLOCKS.md)** · org catalogue: [https://blockchains.github.io/blocks.json](https://blockchains.github.io/blocks.json).

**What it exports**

| Export | Type | Install / access |
|---|---|---|
| `python3 -m blcompose.compose` | cli | `python3 -m blcompose.compose "<idea>" --name <repo> [--out DIR] [--index PATH] [--json result.json] [--create --wait]` |
| `Compose a project` | github-action | `workflow_dispatch inputs: idea, name, request_id → results/<request_id>.json` |

**Minimal example** (the same command CI runs on every push)

```bash
git clone https://github.com/Blockchains/blockchainlab-compose && cd blockchainlab-compose
python3 -m blcompose.compose "A community governance token with permit approvals, vote delegation and an on-chain governor with a timelock" \
  --name my-dao --out /tmp/my-dao --json my-dao.json     # generate + forge test locally, no repo created
```

**Inputs → outputs**

- In: `idea` (string) plain-language description; `--name` (string) new repo name; `--index` (path) local blockchainlab-index checkout (cloned if omitted)
- Out: `Foundry project` (directory) src/, test/, script/Deploy.s.sol, CI, NOTICE, plan.json, component-map.json, plus AGENTS.md, llms.txt and a schema-valid blocks.json derived from the generated contracts; `result JSON` (file) links, capabilities, components, test results; `exit 3` (code) idea needs an unsupported capability

**Composes with**

- [Blockchains/blockchainlab-index](https://github.com/Blockchains/blockchainlab-index): component source (catalog, components, taxonomy)
- [Blockchains/forge-dao-governance-token](https://github.com/Blockchains/forge-dao-governance-token): reference output, re-composed in CI
- [Blockchains/forge-usd-priced-membership-nft](https://github.com/Blockchains/forge-usd-priced-membership-nft): reference output, re-composed in CI
- [Blockchains/grokhack-forge](https://github.com/Blockchains/grokhack-forge): sister composer for Grok apps
- [Blockchains/blockchainlab-sdk](https://github.com/Blockchains/blockchainlab-sdk): add a data layer to a generated dApp

**Versioning & stability:** `beta`. Supported capabilities: fungible-token, token-permit, governance, nft, royalties, price-oracle, pausable, access-control (archetypes token | nft). Anything else exits 3 with the supported list. Components are pinned to fork release tags; generated projects pin solc 0.8.30.
<!-- blocks:end -->

## Configuration

| Variable / flag | Required | Purpose |
|---|---|---|
| `XAI_API_KEY` | no | One Grok review call (`grok-4.7`, fallback `grok-4.5`) written to `REVIEW.md`; skipped when unset |
| `MAINNET_RPC_URL` | no | Enables the generated live-chain fork tests |
| `--index PATH` | no | Use a local blockchainlab-index checkout instead of cloning it |
| `gh` auth as Blockchains | for `--create` | Create and push the new repo |
| `FORGE_TOKEN` (repo secret) | for the Action | Fine-grained PAT; `GITHUB_TOKEN` cannot create repositories |
| `DEPLOYER_PRIVATE_KEY`, `SEPOLIA_RPC_URL` (secrets in generated repos) | for deploy | Used by each generated repo's Sepolia deploy workflow |

## Contributing

Issues and pull requests are welcome. Please read the [contributing guide](https://github.com/Blockchains/.github/blob/main/CONTRIBUTING.md), [code of conduct](https://github.com/Blockchains/.github/blob/main/CODE_OF_CONDUCT.md) and [security policy](https://github.com/Blockchains/.github/blob/main/SECURITY.md) first.

---
Built by Blockchain Lab — [blockchainlab.com](https://blockchainlab.com/?utm_source=github&utm_medium=readme&utm_campaign=blockchainlab-compose)
