"""AI-agent docs for composed repos: AGENTS.md, llms.txt and a blocks.json manifest (Blockchains blocks schema 1.0).

Everything is derived from the generated sources and the component map, so the manifest matches the code:
contracts, constructor signatures and public/external functions are read from src/*.sol.
Schema: https://github.com/Blockchains/.github/blob/main/docs/BLOCKS-SCHEMA.md (vendored copy: blocks.schema.json).
"""
import json, os, re

SCHEMA_URL = "https://raw.githubusercontent.com/Blockchains/.github/main/docs/blocks.schema.json"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "blocks.schema.json")
GUIDE = "https://github.com/Blockchains/.github/blob/main/docs/BUILD-WITH-BLOCKS.md"


def _strip_comments(src):
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", src, flags=re.S)


def parse_contracts(files):
    """[{name, path, constructor, functions, events, errors}] for every contract in src/ (glue written by the composer)."""
    out = []
    for path, src in sorted(files.items()):
        if not (path.startswith("src/") and path.endswith(".sol")):
            continue
        body = _strip_comments(src)
        for m in re.finditer(r"^\s*(?:abstract\s+)?contract\s+(\w+)(?:\s+is\s+([^{]+))?", body, re.M):
            ctor = re.search(r"constructor\s*\(([^)]*)\)", body)
            fns = []
            for f in re.finditer(r"function\s+(\w+)\s*\(([^)]*)\)([^{;]*)", body):
                mods = f.group(3)
                if re.search(r"\b(external|public)\b", mods):
                    params = ",".join(p.split()[0] for p in f.group(2).split(",") if p.strip())
                    fns.append(f"{f.group(1)}({params})")
            pub_vars = [v for v in re.findall(r"^\s*[\w\[\]]+\s+public\s+(?:constant\s+|immutable\s+)?(\w+)\s*[;=]", body, re.M)]
            out.append({"name": m.group(1), "path": path, "bases": [b.strip().split("(")[0] for b in (m.group(2) or "").split(",") if b.strip()],
                        "constructor": " ".join(ctor.group(1).split()) if ctor else "",
                        "functions": sorted(set(fns)) + [f"{v}()" for v in pub_vars if f"{v}()" not in fns],
                        "events": re.findall(r"\bevent\s+(\w+)", body), "errors": re.findall(r"\berror\s+(\w+)", body)})
    return out


def manifest(name, title, idea, arch, features, files, cmap, lic, owner, solc):
    contracts = parse_contracts(files)
    eps = [{"type": "solidity", "name": c["name"], "ref": c["path"], "install": f"forge install {owner}/{name}",
            "usage": f"import {{{c['name']}}} from \"{name}/{os.path.basename(c['path'])}\";  // remapping {name}/=lib/{name}/src/. exports = functions declared here"
                     + (f"; functions inherited from {', '.join(c['bases'])} also apply" if c["bases"] else ""),
            "exports": c["functions"]} for c in contracts]
    eps.append({"type": "file", "name": "script/Deploy.s.sol", "ref": "script/Deploy.s.sol", "usage": "forge script script/Deploy.s.sol --rpc-url $SEPOLIA_RPC_URL --account <keystore> --broadcast"})
    eps.append({"type": "file", "name": "plan.json, component-map.json", "ref": "component-map.json", "usage": "provenance: capability → component → pinned Blockchains fork commit"})
    upstreams = sorted({f["fork"] for f in cmap["copied_files"]})
    summary = f"Composed {arch} contracts: " + "; ".join(features)
    summary = (summary[:396] + "…") if len(summary) > 397 else summary
    return {
        "$schema": SCHEMA_URL, "schema_version": "1.0", "name": name, "repo": f"{owner}/{name}", "summary": summary,
        "kind": ["contracts"], "stability": "experimental", "license": lic["project_license"],
        "entrypoints": eps,
        "inputs": [{"name": f"{c['name']} constructor", "type": "Solidity", "description": f"{c['name']}({c['constructor']})"} for c in contracts if c["constructor"]]
                  + [{"name": "SEPOLIA_RPC_URL / MAINNET_RPC_URL", "type": "env", "description": "deploy target; MAINNET_RPC_URL also enables live fork tests"}],
        "outputs": [{"name": "deployed contracts", "type": "EVM"}]
                   + [{"name": f"{c['name']} events/errors", "type": "ABI", "description": ", ".join(c["events"] + c["errors"]) or "see source"} for c in contracts],
        "deps": [f"foundry (solc {solc})"],
        "compatible_with": [{"repo": "Blockchains/blockchainlab-compose", "how": "the composer that generated this repo (idea → plan → components → glue → tests)"},
                            {"repo": "Blockchains/blockchainlab-index", "how": "where the components and pinned commits came from (plan.json)"},
                            {"repo": "Blockchains/blockchainlab-sdk", "how": "off-chain data for a front end (chains, healthy RPCs, OFAC screening)"}]
                           + [{"repo": f, "how": "source of copied components (pinned commit in component-map.json)"} for f in upstreams if f.startswith("Blockchains/")],
        "tests": {"command": "forge test -vv", "ci": ".github/workflows/ci.yml", "network": False},
        "env": [{"name": "SEPOLIA_RPC_URL", "required": False, "purpose": "deploy RPC"}, {"name": "MAINNET_RPC_URL", "required": False, "purpose": "live-chain fork tests"},
                {"name": "DEPLOYER_PRIVATE_KEY", "required": False, "purpose": "GitHub secret for the Deploy (Sepolia) workflow only; never commit it"}],
        "docs": {"readme": "README.md", "agents": "AGENTS.md", "llms": "llms.txt", "extra": ["plan.json", "component-map.json", "NOTICE"]},
        "tags": ["solidity", "foundry", "composed", arch],
    }


def agents_md(name, title, idea, arch, features, files, owner, solc):
    contracts = parse_contracts(files)
    tests = sorted(p for p in files if p.startswith("test/"))
    rows = "\n".join(f"| `{c['path']}` | `{c['name']}` (generated glue): {', '.join(c['functions'][:8])}{'…' if len(c['functions']) > 8 else ''} |" for c in contracts)
    return f"""# AGENTS.md: {name}

Instructions for AI coding agents working in this repository. Humans: see [README.md](README.md).

**What this is:** {idea.strip()}
Composed by [blockchainlab-compose](https://github.com/Blockchains/blockchainlab-compose) (archetype `{arch}`): {'; '.join(features)}.

## Setup
```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup   # Foundry; solc {solc} is pinned in foundry.toml
forge build
```

## Build / test
```bash
forge test -vv                    # unit + fuzz tests (offline)
MAINNET_RPC_URL=… forge test -vv  # also runs live-chain fork tests, if any
forge script script/Deploy.s.sol --rpc-url $SEPOLIA_RPC_URL --account <keystore> --broadcast
```
CI: `.github/workflows/ci.yml` runs `forge build --sizes` and `forge test` on every push.

## Structure
| Path | What |
|---|---|
{rows}
| `test/` | {', '.join(f'`{t}`' for t in tests)} |
| `script/Deploy.s.sol` | deployment script (reads constructor args from env/defaults) |
| `lib/` | **copied, unmodified** component files from Blockchains forks at pinned commits (see `component-map.json`, `NOTICE`) |
| `plan.json`, `component-map.json` | composer provenance: capabilities → components → fork commit |
| `blocks.json`, `llms.txt` | machine-readable block manifest and doc map |

## Conventions
- Only `src/`, `test/` and `script/` are generated glue; edit those. Never edit files under `lib/`: they are pinned third-party sources (SPDX headers kept).
- Solidity {solc}, `evm_version = cancun`, optimizer 200 runs (foundry.toml). Custom errors over revert strings.
- Every behaviour change needs a test in `test/`; keep `forge test` green.

## Extension points
- Add features by inheriting more OpenZeppelin extensions already present in `lib/` (or re-compose with a richer idea).
- Use this repo as a dependency: `forge install {owner}/{name}` and remap `{name}/=lib/{name}/src/` (plus this repo's remappings in foundry.toml).
- Front end / data: [blockchainlab-sdk](https://github.com/Blockchains/blockchainlab-sdk) (chains, healthy RPCs, OFAC screening). See [Build with Blocks]({GUIDE}).

## Do / don't
- Do run `forge test` before every commit and keep `blocks.json` in sync when you add contracts or public functions.
- Don't commit private keys, `.env` files or RPC URLs with keys. Deploy keys go in GitHub secrets only.
- Don't deploy with real value without an audit: this code is generated and unaudited.
"""


def llms_txt(name, idea, arch, features, files, owner):
    contracts = parse_contracts(files)
    raw = f"https://raw.githubusercontent.com/{owner}/{name}/main"
    idea_s = idea.strip() + ("" if idea.strip()[-1:] in ".!?" else ".")
    lines = [f"# {name}", "", f"> {idea_s} Composed Solidity contracts (archetype `{arch}`, Foundry): {'; '.join(features)}.", "",
             "Generated by blockchainlab-compose from components in blockchainlab-index (pinned Blockchains fork commits). Unaudited.", "",
             "## Docs", f"- [README]({raw}/README.md): features, run, components, licence", f"- [AGENTS.md]({raw}/AGENTS.md): setup, commands, structure, rules for AI agents",
             f"- [blocks.json]({raw}/blocks.json): machine-readable manifest (exports, inputs, outputs, tests)", "", "## Contracts"]
    lines += [f"- [{c['name']}]({raw}/{c['path']}): {', '.join(c['functions'][:6])}" for c in contracts]
    lines += ["", "## Optional", f"- [plan.json]({raw}/plan.json): composition plan", f"- [component-map.json]({raw}/component-map.json): copied files and pinned commits",
              f"- [Build with Blocks]({GUIDE}): how Blockchains blocks fit together", ""]
    return "\n".join(lines)


def write(out, name, title, idea, arch, features, files, cmap, lic, owner, solc):
    m = manifest(name, title, idea, arch, features, files, cmap, lic, owner, solc)
    with open(os.path.join(out, "blocks.json"), "w") as f:
        json.dump(m, f, indent=2, ensure_ascii=False); f.write("\n")
    open(os.path.join(out, "AGENTS.md"), "w").write(agents_md(name, title, idea, arch, features, files, owner, solc))
    open(os.path.join(out, "llms.txt"), "w").write(llms_txt(name, idea, arch, features, files, owner))
    return m


def validate(manifest_obj):
    """Validate against the vendored blocks schema; returns a list of error strings (requires `jsonschema`)."""
    import jsonschema
    schema = json.load(open(SCHEMA_PATH))
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(manifest_obj)]
