import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from blcompose import compose, recipes

GLUED = {
    "ERC721.sol",
    "ERC2981.sol",
    "AccessControl.sol",
    "ERC721Pausable.sol",
    "AggregatorV3Interface.sol",
}


class T(unittest.TestCase):
    def test_pragma(self):
        self.assertTrue(compose.pragma_ok("^0.8.20", "0.8.30"))
        self.assertFalse(compose.pragma_ok("^0.7.6", "0.8.30"))
        self.assertTrue(compose.pragma_ok(">=0.8.4 <0.9.0", "0.8.30"))
        self.assertFalse(compose.pragma_ok("=0.8.19", "0.8.30"))
        self.assertTrue(compose.pragma_ok(">=0.6.2 <0.9.0 || ^0.5.0", "0.8.30"))

    def test_archetype(self):
        self.assertEqual(recipes.choose({"nft", "royalties"}), "nft")
        self.assertEqual(recipes.choose({"governance"}), "token")
        self.assertIsNone(recipes.choose({"amm-dex"}))

    def test_generated_sources_reference_fetched_components(self):
        files, _ = recipes.nft("Club", {"nft", "royalties", "price-oracle", "access-control", "pausable"})
        src = files["src/Club.sol"]
        for slug, path in recipes.needed_components("nft", {"nft", "royalties", "price-oracle", "access-control", "pausable"}):
            if path.split("/")[-1] in GLUED:
                self.assertIn(path.split("/")[-1], src)

if __name__ == "__main__": unittest.main()
