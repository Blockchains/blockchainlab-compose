#!/usr/bin/env python3
"""Blockchain Lab Forge composer: idea -> components (blockchainlab-index) -> compatibility + licence checks
-> glue code + tests + deploy script + CI -> local forge build/test -> (optional) Blockchains/<name> repo -> CI result -> link.

  python3 -m blcompose.compose "<idea>" --name <repo-name> [--out DIR] [--create] [--wait] [--index PATH] [--json result.json]

Stdlib only (plus `forge` and `gh` on PATH). Exit codes: 0 ok, 2 bad input, 3 unsupported idea, 4 compatibility/licence, 5 build/test, 6 CI failed."""
import argparse, importlib.util, json, os, re, shutil, subprocess, sys, time, datetime
from . import recipes

SOLC = "0.8.30"
PINS = {"openzeppelin-contracts": "v5.7.0", "forge-std": "v1.17.0"}
INDEX_REPO = "https://github.com/Blockchains/blockchainlab-index"
OSI_OK = re.compile(r"^(MIT|Apache-2\.0|BSD-[23]-Clause|ISC|Unlicense|0BSD|MPL-2\.0|LGPL-[23]\.[01](-only|-or-later)?|GPL-[23]\.0(-only|-or-later)?|AGPL-3\.0(-only|-or-later)?|CC0-1\.0)$")
RULES = [  # keyword rules on top of the index taxonomy matcher (deterministic)
    (r"\bpaus(e|able|ing)\b|\bkill ?switch\b|\bemergency stop\b", "pausable"),
    (r"\brole[s-]?\b|\bminter\b|\badmins?\b|\bpermission", "access-control"),
    (r"\busd\b|\bchainlink\b|\bprice feed\b|\boracle\b|\bdollar", "price-oracle"),
    (r"\broyalt", "royalties"),
    (r"\bpermit\b|\beip-?2612\b|\bgasless approvals?\b", "token-permit"),
    (r"\bgovern(or|ance)\b|\bdao\b|\bvot(e|ing)\b|\bdelegat", "governance"),
    (r"\bnft\b|\berc-?721\b|\bcollectible|\bmembership (pass|nft|collection)", "nft"),
    (r"\berc-?20\b|\btoken\b", "fungible-token"),
]

def log(*a): print("[forge]", *a, file=sys.stderr, flush=True)
def run(cmd, cwd=None, check=True, timeout=1800, env=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    if check and p.returncode: raise RuntimeError(f"{' '.join(cmd)} -> {p.returncode}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    return p

def load_index(path):
    if not path:
        path = os.path.expanduser("~/.cache/blcompose/blockchainlab-index")
        if os.path.isdir(path): run(["git", "-C", path, "pull", "-q", "--ff-only"], check=False)
        else: run(["git", "clone", "-q", "--depth", "1", INDEX_REPO, path])
    os.environ["BL_INDEX"] = path
    spec = importlib.util.spec_from_file_location("blindex_compose", os.path.join(path, "indexer", "compose.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m, path

def detect(idx, idea):
    pl = idx.plan(idea)
    found = {c["id"]: {"source": "index-taxonomy", "score": c["score"], "why": c["why"]} for c in pl["capabilities"]}
    t = idea.lower()
    for rx, cap in RULES:
        if re.search(rx, t) and cap not in found: found[cap] = {"source": "keyword-rule", "why": [re.search(rx, t).group(0)]}
    if "nft" in found and "fungible-token" in found and found["fungible-token"]["source"] == "keyword-rule": found.pop("fungible-token")
    return pl, found

# ---- compatibility -------------------------------------------------------------------------------
def _v(s): return tuple(int(x) for x in (s.split(".") + ["0", "0"])[:3])
def pragma_ok(expr, ver):
    v = _v(ver)
    for part in expr.split("||"):
        ok = True
        for tok in re.findall(r"(\^|>=|<=|>|<|=|~)?\s*(\d+\.\d+(?:\.\d+)?)", part):
            op, x = tok; xv = _v(x)
            if op == "^": ok &= xv <= v < (xv[0], xv[1] + 1, 0) if xv[0] == 0 else xv <= v < (xv[0] + 1, 0, 0)
            elif op == ">=": ok &= v >= xv
            elif op == ">": ok &= v > xv
            elif op == "<=": ok &= v <= xv
            elif op == "<": ok &= v < xv
            elif op == "~": ok &= xv <= v < (xv[0], xv[1] + 1, 0)
            else: ok &= v == xv
        if ok: return True
    return False

def check_compat(out, files):
    problems, pragmas = [], {}
    for f in files:
        p = os.path.join(out, f["dest"])
        if not p.endswith(".sol"): continue
        m = re.search(r"pragma\s+solidity\s+([^;]+);", open(p).read())
        if m:
            pragmas[f["dest"]] = m.group(1).strip()
            if not pragma_ok(m.group(1), SOLC): problems.append(f"{f['dest']}: pragma {m.group(1)} not satisfied by solc {SOLC}")
        spdx = re.search(r"SPDX-License-Identifier:\s*([^\s*]+)", open(p).read())
        lic = spdx.group(1) if spdx else (f.get("license") or "NOASSERTION")
        f["spdx"] = lic
        ids = [x for x in re.split(r"\s+(?:OR|AND)\s+|[()]", lic) if x]
        if not any(OSI_OK.match(x) for x in ids): problems.append(f"{f['dest']}: licence {lic} is not OSI-approved; refusing to copy")
    return problems, pragmas

# ---- main ------------------------------------------------------------------------------------------
def compose(idea, name, out=None, index=None, create=False, wait=False, owner="Blockchains", local_test=True):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,90}", name or ""): raise SystemExit((2, "invalid repo name"))
    idx, ipath = load_index(index)
    pl, found = detect(idx, idea)
    ignored = {k: v for k, v in found.items() if k not in recipes.SUPPORTED and v.get("why") and all(str(w).startswith("semantic") for w in v["why"])}
    for k in ignored: found.pop(k)  # weak, embedding-only matches for capabilities we cannot generate are reported, not fatal
    caps = set(found)
    unsupported = sorted(caps - recipes.SUPPORTED - {"dev-framework", "math-lib", "signatures", "evm-client-lib", "wallet-ui"})
    arch = recipes.choose(caps)
    res = {"idea": idea, "name": name, "capabilities": found, "ignored_semantic_only": ignored, "archetype": arch, "index": {"path": ipath, "generated_at": idx.cat.get("generated_at")}}
    if not arch or unsupported:
        res["error"] = (f"unsupported capabilities: {unsupported}. " if unsupported else "") + f"Supported today: {sorted(recipes.SUPPORTED)} (EVM token / NFT archetypes). Try blockchainlab-starters for other stacks."
        return 3, res
    feats = caps & recipes.SUPPORTED
    title = recipes.ident(re.sub(r"(?i)^(forge|example)[-_]+|[-_]+(token|nft|app|repo)$", "", name))
    # components: the glue imports these exact files; each must exist in the index (licence, pragma, pinned commit)
    sel = []
    for slug, path in recipes.needed_components(arch, feats) + [("forge-std", "src/Test.sol"), ("forge-std", "src/Script.sol")]:
        comp = next((c for c in idx.load_components(slug) if c["path"] == path), None)
        r = idx.repos.get(slug)
        if not r: res["error"] = f"index has no repo {slug}"; return 4, res
        planned = next((s for s in pl["selected"] if s["slug"] == slug and s["path"] == path), None)
        sel.append({"slug": slug, "path": path, "name": (comp or {}).get("name") or os.path.basename(path)[:-4], "kind": (comp or {}).get("kind", "contract"),
                    "license": (comp or {}).get("spdx") or r.get("license"), "license_class": (comp or {}).get("license_class", "permissive"),
                    "pragma": (comp or {}).get("pragma"), "fork": r["fork"], "upstream": r["upstream"], "commit": r["commit"],
                    "capability": next((cid for cid in sorted(feats) if comp and any(x["id"] == cid for x in comp.get("caps", []))), "dev-framework" if slug == "forge-std" else "support"),
                    "role": "planner-selected" if planned else ("indexed" if comp else "import-target"), "in_index": bool(comp)})
    lic = idx.license_verdict([s for s in sel if s["slug"] != "forge-std"])
    if lic["project_license"] != "MIT": res["error"] = f"licence check: {lic}"; return 4, res
    out = out or os.path.join("/tmp/blcompose", name)
    if os.path.exists(out): shutil.rmtree(out)
    os.makedirs(out)
    planf = os.path.join(out, "plan.json")
    json.dump({"idea": idea, "vm": "EVM", "capabilities": [{"id": k, **v} for k, v in found.items()], "archetype": arch, "selected": sel,
               "planner_selected": pl["selected"], "alternatives": pl["alternatives"], "license": lic, "pins": {k: v for k, v in PINS.items() if any(s["slug"] == k for s in sel)},
               "index_generated_at": idx.cat.get("generated_at")}, open(planf, "w"), indent=1)
    log("fetching", len(sel), "components + import closure from Blockchains forks")
    idx.fetch(planf, out)
    cmap = json.load(open(os.path.join(out, "component-map.json")))
    problems, pragmas = check_compat(out, cmap["copied_files"])
    res["compat"] = {"solc": SOLC, "files": len(cmap["copied_files"]), "problems": problems}
    if problems: return 4, res
    files, features = recipes.ARCHETYPES[arch](title, feats)
    for p, src in files.items():
        os.makedirs(os.path.dirname(os.path.join(out, p)), exist_ok=True); open(os.path.join(out, p), "w").write(src)
    write_project(out, name, title, idea, arch, features, cmap, lic, owner)
    res["files"] = sorted(files)
    res["grok_review"] = grok_review(out, idea, files)
    if local_test and shutil.which("forge"):
        log("forge build + test")
        b = run(["forge", "build", "--sizes"], cwd=out, check=False)
        t = run(["forge", "test", "-vv"], cwd=out, check=False) if b.returncode == 0 else b
        res["local_test"] = {"ok": b.returncode == 0 and t.returncode == 0, "summary": [l for l in t.stdout.splitlines() if "Suite result" in l or "passed" in l][-6:]}
        if not res["local_test"]["ok"]: res["error"] = (b.stderr + t.stdout + t.stderr)[-4000:]; return 5, res
        shutil.rmtree(os.path.join(out, "out"), ignore_errors=True); shutil.rmtree(os.path.join(out, "cache"), ignore_errors=True)
    if create:
        code = publish(out, name, owner, idea, wait, res)
        if code: return code, res
    return 0, res

GROK_MODELS = ("grok-4.7", "grok-4.5")

def grok_review(out, idea, files):
    """Optional: when XAI_API_KEY is in the environment, one real Grok call reviews the generated glue (written to REVIEW.md,
    labelled as an AI review, not an audit). The key is never logged or written. No key -> skipped; 403 -> 'xAI credits needed'."""
    import urllib.request, urllib.error
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key: return {"status": "skipped", "reason": "needs key (XAI_API_KEY not set)"}
    src = "\n\n".join(f"// FILE {p}\n{c}" for p, c in sorted(files.items()) if p.startswith("src/"))[:24000]
    prompt = ("You are reviewing Solidity glue code generated from OpenZeppelin/Chainlink components for this idea: " + idea +
              "\nGive a concise review in Markdown: 1) what the contracts do, 2) up to 6 concrete risks or edge cases with the function name, "
              "3) deployment checklist. No preamble, max 350 words.\n\n" + src)
    last = None
    for model in GROK_MODELS:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 900, "temperature": 0.2}).encode()
        req = urllib.request.Request("https://api.x.ai/v1/chat/completions", data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r: j = json.loads(r.read().decode())
            text = j["choices"][0]["message"]["content"].strip()
            open(os.path.join(out, "REVIEW.md"), "w").write(f"# AI review of the generated glue\n\nWritten by `{j.get('model', model)}` (xAI Grok) when this repo was composed. It is an automated review, **not an audit**.\n\n{text}\n")
            log("grok review written with", j.get("model", model))
            return {"status": "ok", "model": j.get("model", model), "usage": j.get("usage")}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]; last = f"HTTP {e.code}: {msg}"
            if e.code == 403 and re.search(r"credits|spending limit", msg, re.I): return {"status": "credits_needed", "reason": "xAI credits needed: " + msg}
            if e.code in (401,): return {"status": "error", "reason": last}
        except Exception as e:
            last = type(e).__name__
    return {"status": "error", "reason": last}

def write_project(out, name, title, idea, arch, features, cmap, lic, owner):
    rem = sorted(set(cmap["remappings"]) | {"forge-std/=lib/forge-std/src/"})
    open(f"{out}/foundry.toml", "w").write(f"""[profile.default]
src = "src"
out = "out"
libs = ["lib"]
solc = "{SOLC}"
evm_version = "cancun"
optimizer = true
optimizer_runs = 200
remappings = [
{chr(10).join(f'  "{r}",' for r in rem)}
]

[fuzz]
runs = 256

[rpc_endpoints]
mainnet = "${{MAINNET_RPC_URL}}"
sepolia = "${{SEPOLIA_RPC_URL}}"
""")
    open(f"{out}/.gitignore", "w").write("out/\ncache/\nbroadcast/\n.env\n")
    os.makedirs(f"{out}/.github/workflows", exist_ok=True)
    open(f"{out}/.github/workflows/ci.yml", "w").write("""name: CI
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: foundry-rs/foundry-toolchain@v1
      - run: forge --version
      - run: forge build --sizes
      - run: forge test -vv
        env:
          MAINNET_RPC_URL: ${{ secrets.MAINNET_RPC_URL }}
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: |
          curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.28.0/gitleaks_8.28.0_linux_x64.tar.gz | tar xz gitleaks
          ./gitleaks detect --source . --redact --no-banner
""")
    open(f"{out}/.github/workflows/deploy.yml", "w").write("""name: Deploy (Sepolia)
on:
  workflow_dispatch:
    inputs:
      price_feed:
        description: "Chainlink feed address (only used by NFT archetype; Sepolia ETH/USD default)"
        default: "0x694AA1769357215DE4FAC081bf1f309aDC325306"
permissions:
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: foundry-rs/foundry-toolchain@v1
      - name: Require secrets
        env:
          K: ${{ secrets.DEPLOYER_PRIVATE_KEY }}
          R: ${{ secrets.SEPOLIA_RPC_URL }}
        run: |
          if [ -z "$K" ] || [ -z "$R" ]; then echo "::error::Add DEPLOYER_PRIVATE_KEY and SEPOLIA_RPC_URL repository secrets to deploy."; exit 1; fi
      - run: forge script script/Deploy.s.sol --rpc-url "$SEPOLIA_RPC_URL" --private-key "$DEPLOYER_PRIVATE_KEY" --broadcast
        env:
          DEPLOYER_PRIVATE_KEY: ${{ secrets.DEPLOYER_PRIVATE_KEY }}
          SEPOLIA_RPC_URL: ${{ secrets.SEPOLIA_RPC_URL }}
          PRICE_FEED: ${{ inputs.price_feed }}
""")
    open(f"{out}/LICENSE", "w").write(MIT.format(year=datetime.date.today().year))
    srcs = {}
    for f in cmap["copied_files"]: srcs.setdefault((f["fork"], f["commit"], f.get("tag"), f["upstream"]), []).append(f["path"])
    src_rows = "\n".join(f"| [{k[0]}](https://github.com/{k[0]}/tree/{k[1]}) | {k[2] or k[1][:10]} | [{k[3]}](https://github.com/{k[3]}) | {len(v)} |" for k, v in sorted(srcs.items()))
    comp_rows = "\n".join(f"| {s['capability']} | [`{s['name']}`](https://github.com/{s['fork']}/blob/{next((f['commit'] for f in cmap['copied_files'] if f['slug'] == s['slug']), s['commit'])}/{s['path']}) | {s['license']} | {s['role']} |" for s in cmap["selected"] if s["slug"] != "forge-std")
    caps = ", ".join(f"`{c['id']}` ({c.get('source')})" for c in cmap["capabilities"])
    open(f"{out}/README.md", "w").write(f"""# {name}

[![CI](https://github.com/{owner}/{name}/actions/workflows/ci.yml/badge.svg)](https://github.com/{owner}/{name}/actions/workflows/ci.yml) [![Open in Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/{owner}/{name}?quickstart=1)

> **Idea:** {idea}

Composed end to end by [blockchainlab-compose](https://github.com/Blockchains/blockchainlab-compose) (the Blockchain Lab `/forge` engine), with no hand edits:
capabilities detected ({caps}) → archetype `{arch}` → components picked from [blockchainlab-index](https://github.com/Blockchains/blockchainlab-index) → exact source files (plus import closure) copied from the Blockchains forks at pinned commits → pragma check against solc {SOLC} and licence check → generated glue, tests, deploy script and CI → `forge build && forge test` → repo created → CI.

## Features
{chr(10).join('- ' + x for x in features)}

## Run
```bash
git clone https://github.com/{owner}/{name} && cd {name}
forge test -vv                      # unit tests; set MAINNET_RPC_URL to also run live-chain fork tests
forge script script/Deploy.s.sol --rpc-url $SEPOLIA_RPC_URL --account <keystore> --broadcast
```
Or run the **Deploy (Sepolia)** workflow after adding `DEPLOYER_PRIVATE_KEY` and `SEPOLIA_RPC_URL` secrets.

## Components
| Capability | Component | Licence | How chosen |
|---|---|---|---|
{comp_rows}

| Fork | Pinned | Upstream | Files copied |
|---|---|---|---|
{src_rows}

Every copied file is unmodified and keeps its SPDX header; see [NOTICE](NOTICE). If the composer had an xAI key, [`REVIEW.md`](REVIEW.md) holds an automated Grok review of the glue (not an audit). Machine-readable: [`plan.json`](plan.json), [`component-map.json`](component-map.json).

## Licence
{lic['project_license']} for the generated glue. {lic.get('warning') or 'All copied components are permissively licensed.'}

Not audited. Review before deploying with real value.
""")

MIT = """MIT License

Copyright (c) {year} Blockchains

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

def publish(out, name, owner, idea, wait, res):
    gl = shutil.which("gitleaks") or "/workspace/grokforge/bin/gitleaks"
    run(["git", "init", "-q", "-b", "main"], cwd=out)
    run(["git", "add", "-A"], cwd=out)
    env = {**os.environ, "GIT_AUTHOR_NAME": "Blockchain Lab Forge", "GIT_COMMITTER_NAME": "Blockchain Lab Forge",
           "GIT_AUTHOR_EMAIL": "11951015+Blockchains@users.noreply.github.com", "GIT_COMMITTER_EMAIL": "11951015+Blockchains@users.noreply.github.com"}
    run(["git", "commit", "-q", "-m", f"Compose: {idea[:120]}"], cwd=out, env=env)
    if os.path.exists(gl):
        g = run([gl, "detect", "--source", out, "--redact", "--no-banner"], check=False)
        res["gitleaks"] = "clean" if g.returncode == 0 else "LEAKS"
        if g.returncode: res["error"] = "gitleaks found secrets; not pushing"; return 4
    else: res["gitleaks"] = "skipped (gitleaks not installed)"
    full = f"{owner}/{name}"
    exists = run(["gh", "repo", "view", full], check=False).returncode == 0
    if exists: res["error"] = f"{full} already exists; choose another --name"; return 2
    run(["gh", "repo", "create", full, "--public", "--description", ("Forge-composed: " + idea)[:300], "--source", out, "--push", "--remote", "origin"])
    res["repo"] = f"https://github.com/{full}"
    log("created", res["repo"])
    if not wait: return 0
    sha = run(["git", "rev-parse", "HEAD"], cwd=out).stdout.strip()
    for _ in range(90):
        time.sleep(20)
        p = run(["gh", "run", "list", "-R", full, "--commit", sha, "--json", "databaseId,status,conclusion,name,url"], check=False)
        runs = [r for r in json.loads(p.stdout or "[]") if r["name"] == "CI"]
        if runs and runs[0]["status"] == "completed":
            res["ci"] = {"conclusion": runs[0]["conclusion"], "url": runs[0]["url"]}
            return 0 if runs[0]["conclusion"] == "success" else 6
    res["ci"] = {"conclusion": "timeout"}; return 6

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idea"); ap.add_argument("--name", required=True); ap.add_argument("--out"); ap.add_argument("--index")
    ap.add_argument("--owner", default="Blockchains"); ap.add_argument("--create", action="store_true"); ap.add_argument("--wait", action="store_true")
    ap.add_argument("--no-local-test", action="store_true"); ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        code, res = compose(a.idea, a.name, a.out, a.index, a.create, a.wait, a.owner, not a.no_local_test)
    except SystemExit as e:
        if isinstance(e.code, tuple): code, res = e.code[0], {"error": e.code[1]}
        else: raise
    res["exit_code"] = code
    s = json.dumps(res, indent=1, default=str)
    if a.json: open(a.json, "w").write(s)
    print(s)
    return code

if __name__ == "__main__": sys.exit(main())
