# blockchainlab-compose

[![CI](https://github.com/Blockchains/blockchainlab-compose/actions/workflows/ci.yml/badge.svg)](https://github.com/Blockchains/blockchainlab-compose/actions/workflows/ci.yml)

The engine behind **[blockchainlab.com /forge](https://blockchainlab.com/forge)**. Describe a project in plain language; it picks components from
the Blockchains forks, checks they fit together, writes the glue code, tests, deploy script and CI, creates the repo under
[github.com/Blockchains](https://github.com/Blockchains), waits for CI and returns the link.

```
idea ─► capabilities: blockchainlab-index taxonomy matcher (+ optional bge-small semantic match) + deterministic keyword rules
     ─► archetype (token | nft)                       unsupported capability → exit 3 with the list of what is supported
     ─► components: exact files the glue imports, each looked up in blockchainlab-index (licence, pragma, pinned commit)
     ─► fetch: files + full import closure copied unmodified from the Blockchains forks at pinned release tags (NOTICE written)
     ─► compatibility: every pragma must accept solc 0.8.30; every SPDX id must be OSI; project licence verdict (GPL → refused for now)
     ─► generate: glue contracts, Foundry tests (unit + live-chain fork test when MAINNET_RPC_URL is set), Deploy.s.sol, CI, Sepolia deploy workflow, README
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
