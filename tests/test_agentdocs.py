import json, os, sys, tempfile, unittest, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blcompose import agentdocs, recipes

CMAP = {"copied_files": [{"fork": "Blockchains/openzeppelin-contracts", "commit": "cab19933", "slug": "openzeppelin-contracts", "path": "contracts/token/ERC721/ERC721.sol", "upstream": "OpenZeppelin/openzeppelin-contracts"}]}
LIC = {"project_license": "MIT"}
CASES = [("nft", {"nft", "royalties", "price-oracle", "access-control", "pausable"}, "Club", ["Club"]),
         ("token", {"governance", "permit"}, "Club", ["ClubGovernor", "ClubToken"])]


class AgentDocs(unittest.TestCase):
    def test_manifest_schema_valid_and_matches_code(self):
        for arch, feats, title, contracts in CASES:
            files, features = recipes.ARCHETYPES[arch](title, feats)
            m = agentdocs.manifest(f"ci-{arch}", title, "An idea", arch, features, files, CMAP, LIC, "Blockchains", "0.8.30")
            self.assertEqual(agentdocs.validate(m), [], arch)
            sol = [e for e in m["entrypoints"] if e["type"] == "solidity"]
            self.assertEqual(sorted(e["name"] for e in sol), contracts)
            for e in sol:   # every exported function really is declared external/public in the generated source
                src = files[e["ref"]]
                self.assertTrue(e["exports"], e["name"])
                for fn in e["exports"]:
                    self.assertRegex(src, rf"\b{fn.split('(')[0]}\b")
        files, features = recipes.ARCHETYPES["nft"]("Club", CASES[0][1])
        m = agentdocs.manifest("ci-nft", "Club", "x", "nft", features, files, CMAP, LIC, "Blockchains", "0.8.30")
        exports = next(e for e in m["entrypoints"] if e["name"] == "Club")["exports"]
        self.assertIn("mint()", exports)
        self.assertTrue(any(i["description"].startswith("Club(address admin") for i in m["inputs"]))

    def test_write_emits_three_files(self):
        files, features = recipes.ARCHETYPES["token"]("Club", CASES[1][1])
        with tempfile.TemporaryDirectory() as d:
            agentdocs.write(d, "ci-token", "Club", "A governance token", "token", features, files, CMAP, LIC, "Blockchains", "0.8.30")
            self.assertEqual(sorted(os.listdir(d)), ["AGENTS.md", "blocks.json", "llms.txt"])
            self.assertEqual(agentdocs.validate(json.load(open(os.path.join(d, "blocks.json")))), [])
            with open(os.path.join(d, "AGENTS.md")) as f: agents = f.read()
            for s in ("## Setup", "## Build / test", "## Structure", "## Conventions", "## Extension points", "## Do / don't", "src/ClubToken.sol", "forge test"):
                self.assertIn(s, agents)
            with open(os.path.join(d, "llms.txt")) as f: llms = f.read()
            self.assertTrue(llms.startswith("# ci-token\n\n> "))   # llmstxt.org: H1 then blockquote summary
            self.assertIn("raw.githubusercontent.com/Blockchains/ci-token/main/AGENTS.md", llms)
            self.assertIn("> A governance token. Composed", llms)

    def test_vendored_schema_matches_published(self):
        try:
            live = json.load(urllib.request.urlopen(agentdocs.SCHEMA_URL, timeout=20))
        except Exception as e:  # offline: skip, CI has network
            self.skipTest(f"schema not reachable: {e}")
        self.assertEqual(json.load(open(agentdocs.SCHEMA_PATH)), live, "blcompose/blocks.schema.json is stale; copy Blockchains/.github docs/blocks.schema.json")


if __name__ == "__main__": unittest.main()
