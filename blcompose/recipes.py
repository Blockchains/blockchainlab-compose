"""Deterministic Solidity code generation for Blockchain Lab Forge.
Each archetype turns a set of capability ids (from the blockchainlab-index taxonomy) into glue contracts,
Foundry tests and a deploy script that use the exact OpenZeppelin / Chainlink files fetched from the Blockchains forks."""
import re

OZ = "@openzeppelin/contracts"
CL = "@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol"

def ident(s, default="Composed"):
    w = re.findall(r"[A-Za-z0-9]+", s or "")
    out = "".join(x[:1].upper() + x[1:] for x in w)[:40]
    if not out or out[0].isdigit(): out = default + out
    return out

def symbol(name):
    caps = "".join(ch for ch in name if ch.isupper())
    return (caps or name[:4]).upper()[:6]

# --------------------------------------------------------------------------------------------
# archetype: fungible token (+permit, +votes/governor+timelock, +pausable, roles|ownable)
# --------------------------------------------------------------------------------------------
def token(name, f):
    sym = symbol(name); gov = "governance" in f; permit = "token-permit" in f or gov; pause = "pausable" in f
    roles = "access-control" in f or gov
    imps = [f"{OZ}/token/ERC20/ERC20.sol"]
    bases = ["ERC20"]; ctor = [f'ERC20("{name}", "{sym}")']
    if permit: imps.append(f"{OZ}/token/ERC20/extensions/ERC20Permit.sol"); bases.append("ERC20Permit"); ctor.append(f'ERC20Permit("{name}")')
    if gov: imps.append(f"{OZ}/token/ERC20/extensions/ERC20Votes.sol"); bases.append("ERC20Votes")
    if pause: imps += [f"{OZ}/token/ERC20/extensions/ERC20Pausable.sol"]; bases.append("ERC20Pausable")
    if roles: imps.append(f"{OZ}/access/AccessControl.sol"); bases.append("AccessControl")
    else: imps.append(f"{OZ}/access/Ownable.sol"); bases.append("Ownable"); ctor.append("Ownable(admin)")
    if gov and permit: imps.append(f"{OZ}/utils/Nonces.sol")
    guard_mint = "onlyRole(MINTER_ROLE)" if roles else "onlyOwner"
    guard_pause = "onlyRole(PAUSER_ROLE)" if roles else "onlyOwner"
    body = []
    if roles:
        body.append('    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");')
        if pause: body.append('    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");')
    body.append("    /// @notice Hard cap on total supply (18 decimals).\n    uint256 public immutable cap;\n    error CapExceeded(uint256 requested, uint256 cap);\n")
    grants = ""
    if roles:
        grants = "        _grantRole(DEFAULT_ADMIN_ROLE, admin);\n        _grantRole(MINTER_ROLE, admin);\n" + ("        _grantRole(PAUSER_ROLE, admin);\n" if pause else "")
    body.append(f"""    constructor(address admin, uint256 initialSupply, uint256 cap_)
        {' '.join(ctor)}
    {{
        require(cap_ >= initialSupply, "cap < initial supply");
        cap = cap_;
{grants}        _mint(admin, initialSupply);
    }}

    function mint(address to, uint256 amount) external {guard_mint} {{
        if (totalSupply() + amount > cap) revert CapExceeded(totalSupply() + amount, cap);
        _mint(to, amount);
    }}
""")
    if pause:
        body.append(f"    function pause() external {guard_pause} {{ _pause(); }}\n    function unpause() external {guard_pause} {{ _unpause(); }}\n")
    ov = [b for b in ("ERC20", "ERC20Votes", "ERC20Pausable") if b in bases]
    if len(ov) > 1:
        body.append(f"    function _update(address from, address to, uint256 value) internal override({', '.join(ov)}) {{\n        super._update(from, to, value);\n    }}\n")
    if gov:
        body.append("    function nonces(address owner) public view override(ERC20Permit, Nonces) returns (uint256) {\n        return super.nonces(owner);\n    }\n")
    tok = f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

{chr(10).join(f'import "{i}";' for i in imps)}

/// @title {name}
/// @notice Composed by Blockchain Lab Forge from OpenZeppelin Contracts (via Blockchains/openzeppelin-contracts).
contract {name}Token is {', '.join(bases)} {{
{chr(10).join(body)}}}
"""
    files = {f"src/{name}Token.sol": tok}
    if gov: files[f"src/{name}Governor.sol"] = governor(name)
    files[f"test/{name}Token.t.sol"] = token_test(name, permit, gov, pause, roles)
    files["script/Deploy.s.sol"] = token_deploy(name, gov, roles)
    features = ["ERC-20 with supply cap"] + (["EIP-2612 permit"] if permit else []) + (["ERC20Votes delegation", "Governor + TimelockController"] if gov else []) + (["pausable transfers"] if pause else []) + (["role-based minting (AccessControl)"] if roles else ["owner-only minting (Ownable)"])
    return files, features

def governor(name):
    return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "{OZ}/governance/Governor.sol";
import "{OZ}/governance/extensions/GovernorSettings.sol";
import "{OZ}/governance/extensions/GovernorCountingSimple.sol";
import "{OZ}/governance/extensions/GovernorVotes.sol";
import "{OZ}/governance/extensions/GovernorVotesQuorumFraction.sol";
import "{OZ}/governance/extensions/GovernorTimelockControl.sol";

/// @notice On-chain governor for {name}Token: 1 block delay, ~1 week voting (50400 blocks), 4% quorum, timelocked execution.
contract {name}Governor is Governor, GovernorSettings, GovernorCountingSimple, GovernorVotes, GovernorVotesQuorumFraction, GovernorTimelockControl {{
    constructor(IVotes token, TimelockController timelock, uint48 votingDelay_, uint32 votingPeriod_)
        Governor("{name} Governor")
        GovernorSettings(votingDelay_, votingPeriod_, 0)
        GovernorVotes(token)
        GovernorVotesQuorumFraction(4)
        GovernorTimelockControl(timelock)
    {{}}

    function state(uint256 proposalId) public view override(Governor, GovernorTimelockControl) returns (ProposalState) {{
        return super.state(proposalId);
    }}

    function proposalNeedsQueuing(uint256 proposalId) public view override(Governor, GovernorTimelockControl) returns (bool) {{
        return super.proposalNeedsQueuing(proposalId);
    }}

    function proposalThreshold() public view override(Governor, GovernorSettings) returns (uint256) {{
        return super.proposalThreshold();
    }}

    function _queueOperations(uint256 proposalId, address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        internal override(Governor, GovernorTimelockControl) returns (uint48)
    {{
        return super._queueOperations(proposalId, targets, values, calldatas, descriptionHash);
    }}

    function _executeOperations(uint256 proposalId, address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        internal override(Governor, GovernorTimelockControl)
    {{
        super._executeOperations(proposalId, targets, values, calldatas, descriptionHash);
    }}

    function _cancel(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        internal override(Governor, GovernorTimelockControl) returns (uint256)
    {{
        return super._cancel(targets, values, calldatas, descriptionHash);
    }}

    function _executor() internal view override(Governor, GovernorTimelockControl) returns (address) {{
        return super._executor();
    }}
}}
"""

def token_test(name, permit, gov, pause, roles):
    T = f"{name}Token"
    imps = [f'import "../src/{T}.sol";']
    if gov: imps += [f'import "../src/{name}Governor.sol";', f'import "{OZ}/governance/TimelockController.sol";', f'import "{OZ}/governance/IGovernor.sol";']
    if roles: imps.append(f'import "{OZ}/access/IAccessControl.sol";')
    else: imps.append(f'import "{OZ}/access/Ownable.sol";')
    t = [f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
{chr(10).join(imps)}

contract {T}Test is Test {{
    {T} token;
    address admin = makeAddr("admin");
    address alice;
    uint256 aliceKey;
    address bob = makeAddr("bob");
    uint256 constant SUPPLY = 1_000_000e18;
    uint256 constant CAP = 10_000_000e18;

    function setUp() public {{
        (alice, aliceKey) = makeAddrAndKey("alice");
        token = new {T}(admin, SUPPLY, CAP);
    }}

    function test_initialSupplyAndMetadata() public view {{
        assertEq(token.totalSupply(), SUPPLY);
        assertEq(token.balanceOf(admin), SUPPLY);
        assertEq(token.decimals(), 18);
        assertEq(token.cap(), CAP);
    }}

    function test_transfer() public {{
        vm.prank(admin);
        token.transfer(alice, 100e18);
        assertEq(token.balanceOf(alice), 100e18);
    }}

    function test_mintRespectsCap() public {{
        vm.startPrank(admin);
        token.mint(bob, CAP - SUPPLY);
        assertEq(token.totalSupply(), CAP);
        vm.expectRevert(abi.encodeWithSelector({T}.CapExceeded.selector, CAP + 1, CAP));
        token.mint(bob, 1);
        vm.stopPrank();
    }}

    function test_onlyMinterCanMint() public {{
        {"vm.expectRevert(abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, bob, token.MINTER_ROLE()));" if roles else "vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, bob));"}
        vm.prank(bob);
        token.mint(bob, 1);
    }}

    function testFuzz_transfer(uint96 amount) public {{
        vm.assume(amount <= SUPPLY);
        vm.prank(admin);
        token.transfer(bob, amount);
        assertEq(token.balanceOf(bob), amount);
        assertEq(token.balanceOf(admin), SUPPLY - amount);
    }}
"""]
    if permit:
        t.append(f"""
    function test_permitSetsAllowanceFromSignature() public {{
        bytes32 PERMIT_TYPEHASH = keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 structHash = keccak256(abi.encode(PERMIT_TYPEHASH, alice, bob, 50e18, token.nonces(alice), deadline));
        bytes32 digest = keccak256(abi.encodePacked("\\x19\\x01", token.DOMAIN_SEPARATOR(), structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(aliceKey, digest);
        token.permit(alice, bob, 50e18, deadline, v, r, s);
        assertEq(token.allowance(alice, bob), 50e18);
        assertEq(token.nonces(alice), 1);
        vm.expectRevert();
        token.permit(alice, bob, 50e18, deadline, v, r, s); // replay rejected
    }}
""")
    if pause:
        guard = "vm.prank(admin);"
        t.append(f"""
    function test_pauseBlocksTransfers() public {{
        {guard}
        token.pause();
        vm.prank(admin);
        vm.expectRevert();
        token.transfer(alice, 1);
        {guard}
        token.unpause();
        vm.prank(admin);
        token.transfer(alice, 1);
        assertEq(token.balanceOf(alice), 1);
    }}
""")
    if gov:
        t.append(f"""
    function test_delegationGivesVotingPower() public {{
        vm.prank(admin);
        token.transfer(alice, 300e18);
        vm.prank(alice);
        token.delegate(alice);
        assertEq(token.getVotes(alice), 300e18);
        vm.prank(alice);
        token.delegate(bob);
        assertEq(token.getVotes(alice), 0);
        assertEq(token.getVotes(bob), 300e18);
    }}

    /// Full lifecycle: delegate -> propose (timelock mints to bob) -> vote -> queue -> execute.
    function test_governorProposalExecutesThroughTimelock() public {{
        address[] memory proposers = new address[](0);
        address[] memory executors = new address[](1);
        TimelockController timelock = new TimelockController(1 days, proposers, executors, address(this));
        {name}Governor gov = new {name}Governor(token, timelock, 1, 50400);
        timelock.grantRole(timelock.PROPOSER_ROLE(), address(gov));
        timelock.grantRole(timelock.CANCELLER_ROLE(), address(gov));
        bytes32 minterRole = token.MINTER_ROLE();
        vm.prank(admin);
        token.grantRole(minterRole, address(timelock));

        vm.prank(admin);
        token.delegate(admin);
        vm.roll(vm.getBlockNumber() + 1);

        address[] memory targets = new address[](1); targets[0] = address(token);
        uint256[] memory values = new uint256[](1);
        bytes[] memory calldatas = new bytes[](1); calldatas[0] = abi.encodeCall({T}.mint, (bob, 1234e18));
        string memory description = "Mint 1234 tokens to bob";
        vm.prank(admin);
        uint256 id = gov.propose(targets, values, calldatas, description);
        assertEq(uint8(gov.state(id)), uint8(IGovernor.ProposalState.Pending));

        vm.roll(vm.getBlockNumber() + gov.votingDelay() + 1);
        vm.prank(admin);
        gov.castVote(id, 1);
        vm.roll(vm.getBlockNumber() + gov.votingPeriod() + 1);
        assertEq(uint8(gov.state(id)), uint8(IGovernor.ProposalState.Succeeded));

        bytes32 descHash = keccak256(bytes(description));
        gov.queue(targets, values, calldatas, descHash);
        vm.warp(vm.getBlockTimestamp() + 1 days + 1);
        gov.execute(targets, values, calldatas, descHash);
        assertEq(uint8(gov.state(id)), uint8(IGovernor.ProposalState.Executed));
        assertEq(token.balanceOf(bob), 1234e18);
    }}
""")
    t.append("}\n")
    return "".join(t)

def token_deploy(name, gov, roles):
    T = f"{name}Token"
    extra_imp = f'import "../src/{name}Governor.sol";\nimport "{OZ}/governance/TimelockController.sol";\n' if gov else ""
    gov_code = f"""
        address[] memory proposers = new address[](0);
        address[] memory executors = new address[](1); // address(0) = anyone may execute after the delay
        TimelockController timelock = new TimelockController(vm.envOr("TIMELOCK_DELAY", uint256(2 days)), proposers, executors, admin);
        {name}Governor gov = new {name}Governor(token, timelock, 7200, 50400);
        timelock.grantRole(timelock.PROPOSER_ROLE(), address(gov));
        timelock.grantRole(timelock.CANCELLER_ROLE(), address(gov));
        token.grantRole(token.MINTER_ROLE(), address(timelock));
        console2.log("timelock", address(timelock));
        console2.log("governor", address(gov));""" if gov else ""
    return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/{T}.sol";
{extra_imp}
/// forge script script/Deploy.s.sol --rpc-url $RPC_URL --account <keystore> --broadcast
contract Deploy is Script {{
    function run() external {{
        vm.startBroadcast();
        address admin = msg.sender;
        {T} token = new {T}(admin, vm.envOr("INITIAL_SUPPLY", uint256(1_000_000e18)), vm.envOr("SUPPLY_CAP", uint256(10_000_000e18)));
        console2.log("token", address(token));{gov_code}
        vm.stopBroadcast();
    }}
}}
"""

# --------------------------------------------------------------------------------------------
# archetype: NFT (+royalties, +USD price via Chainlink, +pausable, roles|ownable)
# --------------------------------------------------------------------------------------------
def nft(name, f):
    sym = symbol(name); roy = "royalties" in f; oracle = "price-oracle" in f; pause = "pausable" in f; roles = "access-control" in f
    imps = [f"{OZ}/token/ERC721/ERC721.sol"]; bases = ["ERC721"]; ctor = [f'ERC721("{name}", "{sym}")']
    if roy: imps.append(f"{OZ}/token/common/ERC2981.sol"); bases.append("ERC2981")
    if pause: imps.append(f"{OZ}/token/ERC721/extensions/ERC721Pausable.sol"); bases.append("ERC721Pausable")
    if roles: imps.append(f"{OZ}/access/AccessControl.sol"); bases.append("AccessControl")
    else: imps.append(f"{OZ}/access/Ownable.sol"); bases.append("Ownable"); ctor.append("Ownable(admin)")
    if oracle: imps.append(CL)
    G = (lambda r: f"onlyRole({r})") if roles else (lambda r: "onlyOwner")
    adm = "DEFAULT_ADMIN_ROLE"
    b = []
    if roles: b.append('    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");' + ('\n    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");' if pause else ""))
    b.append("    uint256 public immutable maxSupply;\n    uint256 public totalMinted;\n    string private baseURI_;\n    error SoldOut();")
    if oracle:
        b.append("""    AggregatorV3Interface public immutable priceFeed;
    /// @notice Mint price in USD with 18 decimals (e.g. 25e18 = $25).
    uint256 public mintPriceUsd;
    /// @notice Oracle answers older than this are rejected.
    uint256 public maxPriceAge;
    error StaleOrInvalidPrice(int256 answer, uint256 updatedAt);
    error InsufficientPayment(uint256 sent, uint256 required);
    event MintPriceUsdSet(uint256 priceUsd);""")
    params = ["address admin", "uint256 maxSupply_", "string memory baseURI"] + (["address feed", "uint256 mintPriceUsd_", "uint256 maxPriceAge_"] if oracle else []) + (["address royaltyReceiver", "uint96 royaltyBps"] if roy else [])
    init = "        maxSupply = maxSupply_;\n        baseURI_ = baseURI;\n"
    if roles: init += "        _grantRole(DEFAULT_ADMIN_ROLE, admin);\n        _grantRole(MINTER_ROLE, admin);\n" + ("        _grantRole(PAUSER_ROLE, admin);\n" if pause else "")
    if oracle: init += "        priceFeed = AggregatorV3Interface(feed);\n        mintPriceUsd = mintPriceUsd_;\n        maxPriceAge = maxPriceAge_;\n"
    if roy: init += "        _setDefaultRoyalty(royaltyReceiver, royaltyBps);\n"
    b.append(f"""
    constructor({', '.join(params)})
        {' '.join(ctor)}
    {{
{init}    }}

    function _mintNext(address to) internal returns (uint256 id) {{
        if (totalMinted >= maxSupply) revert SoldOut();
        id = ++totalMinted;
        _safeMint(to, id);
    }}

    /// @notice Free mint by an authorised minter (airdrops, comps).
    function mintTo(address to) external {G('MINTER_ROLE')} returns (uint256) {{
        return _mintNext(to);
    }}

    function _baseURI() internal view override returns (string memory) {{
        return baseURI_;
    }}

    function setBaseURI(string calldata u) external {G(adm)} {{
        baseURI_ = u;
    }}
""")
    if oracle:
        b.append(f"""    /// @notice Current mint price in wei, from the Chainlink feed (USD per native token).
    function mintPriceWei() public view returns (uint256) {{
        (, int256 answer,, uint256 updatedAt,) = priceFeed.latestRoundData();
        if (answer <= 0 || updatedAt == 0 || block.timestamp - updatedAt > maxPriceAge) revert StaleOrInvalidPrice(answer, updatedAt);
        return (mintPriceUsd * 10 ** priceFeed.decimals() + uint256(answer) - 1) / uint256(answer); // round up
    }}

    /// @notice Public paid mint. Excess payment is refunded.
    function mint() external payable returns (uint256 id) {{
        uint256 price = mintPriceWei();
        if (msg.value < price) revert InsufficientPayment(msg.value, price);
        id = _mintNext(msg.sender);
        if (msg.value > price) {{
            (bool ok,) = msg.sender.call{{value: msg.value - price}}("");
            require(ok, "refund failed");
        }}
    }}

    function setMintPriceUsd(uint256 p) external {G(adm)} {{
        mintPriceUsd = p;
        emit MintPriceUsdSet(p);
    }}

    function withdraw(address payable to) external {G(adm)} {{
        (bool ok,) = to.call{{value: address(this).balance}}("");
        require(ok, "withdraw failed");
    }}
""")
    if roy:
        b.append(f"    function setDefaultRoyalty(address receiver, uint96 bps) external {G(adm)} {{\n        _setDefaultRoyalty(receiver, bps);\n    }}\n")
    if pause:
        b.append(f"    function pause() external {G('PAUSER_ROLE')} {{ _pause(); }}\n    function unpause() external {G('PAUSER_ROLE')} {{ _unpause(); }}\n")
        b.append("    function _update(address to, uint256 tokenId, address auth) internal override(ERC721, ERC721Pausable) returns (address) {\n        return super._update(to, tokenId, auth);\n    }\n")
    si = [x for x in ("ERC721", "ERC2981", "AccessControl") if x in bases]
    if len(si) > 1:
        b.append(f"    function supportsInterface(bytes4 interfaceId) public view override({', '.join(si)}) returns (bool) {{\n        return super.supportsInterface(interfaceId);\n    }}\n")
    src = f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

{chr(10).join(f'import "{i}";' for i in imps)}

/// @title {name}
/// @notice Composed by Blockchain Lab Forge from OpenZeppelin Contracts{' and Chainlink' if oracle else ''} (via the Blockchains forks).
contract {name} is {', '.join(bases)} {{
{chr(10).join(b)}}}
"""
    files = {f"src/{name}.sol": src, f"test/{name}.t.sol": nft_test(name, roy, oracle, pause, roles), "script/Deploy.s.sol": nft_deploy(name, roy, oracle)}
    if oracle: files["test/utils/FixedPriceAggregator.sol"] = AGG
    features = ["ERC-721 with max supply"] + (["ERC-2981 royalties"] if roy else []) + (["paid mint priced in USD via Chainlink feed (staleness-checked, refunds excess)"] if oracle else []) + (["pausable transfers"] if pause else []) + (["role-based minting (AccessControl)"] if roles else ["owner-only admin (Ownable)"])
    return files, features

AGG = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@chainlink/contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol";

/// Test double implementing the real Chainlink AggregatorV3Interface (used only in unit tests;
/// the fork test in the same suite reads the live ETH/USD feed when MAINNET_RPC_URL is set).
contract FixedPriceAggregator is AggregatorV3Interface {
    int256 public answer;
    uint256 public updatedAt;
    constructor(int256 a) { set(a, block.timestamp); }
    function set(int256 a, uint256 t) public { answer = a; updatedAt = t; }
    function decimals() external pure returns (uint8) { return 8; }
    function description() external pure returns (string memory) { return "ETH / USD (test)"; }
    function version() external pure returns (uint256) { return 4; }
    function getRoundData(uint80 id) external view returns (uint80, int256, uint256, uint256, uint80) { return (id, answer, updatedAt, updatedAt, id); }
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) { return (1, answer, updatedAt, updatedAt, 1); }
}
"""

def nft_test(name, roy, oracle, pause, roles):
    args = ["admin", "MAX", '"ipfs://base/"'] + (["address(feed)", "25e18", "1 hours"] if oracle else []) + (["admin", "500"] if roy else [])
    t = [f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../src/{name}.sol";
{'import "./utils/FixedPriceAggregator.sol";' if oracle else ''}
{'import "@openzeppelin/contracts/access/IAccessControl.sol";' if roles else 'import "@openzeppelin/contracts/access/Ownable.sol";'}
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";

contract {name}Test is Test {{
    {name} nft;
    address admin = makeAddr("admin");
    address alice = makeAddr("alice");
    uint256 constant MAX = 3;
    {'FixedPriceAggregator feed;' if oracle else ''}

    function setUp() public {{
        vm.warp(1_700_000_000);
        {'feed = new FixedPriceAggregator(2500e8); // $2,500 per ETH' if oracle else ''}
        nft = new {name}({', '.join(args)});
    }}

    function test_minterMintsAndTokenURI() public {{
        vm.prank(admin);
        uint256 id = nft.mintTo(alice);
        assertEq(id, 1);
        assertEq(nft.ownerOf(1), alice);
        assertEq(nft.tokenURI(1), "ipfs://base/1");
    }}

    function test_onlyMinter() public {{
        {"vm.expectRevert(abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, alice, nft.MINTER_ROLE()));" if roles else "vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, alice));"}
        vm.prank(alice);
        nft.mintTo(alice);
    }}

    function test_maxSupply() public {{
        vm.startPrank(admin);
        for (uint256 i; i < MAX; i++) nft.mintTo(alice);
        vm.expectRevert({name}.SoldOut.selector);
        nft.mintTo(alice);
        vm.stopPrank();
    }}

    function test_supportsInterfaces() public view {{
        assertTrue(nft.supportsInterface(type(IERC721).interfaceId));
        {'assertTrue(nft.supportsInterface(0x2a55205a)); // ERC-2981' if roy else ''}
    }}
"""]
    if roy:
        t.append("""
    function test_royaltyInfo() public view {
        (address r, uint256 amt) = nft.royaltyInfo(1, 10_000);
        assertEq(r, admin);
        assertEq(amt, 500); // 5%
    }
""")
    if oracle:
        t.append(f"""
    function test_priceFromFeed() public view {{
        // $25 at $2,500/ETH = 0.01 ETH
        assertEq(nft.mintPriceWei(), 0.01 ether);
    }}

    function test_paidMintRefundsExcess() public {{
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        nft.mint{{value: 0.05 ether}}();
        assertEq(nft.ownerOf(1), alice);
        assertEq(alice.balance, 1 ether - 0.01 ether);
        assertEq(address(nft).balance, 0.01 ether);
        uint256 before = admin.balance;
        vm.prank(admin);
        nft.withdraw(payable(admin));
        assertEq(admin.balance - before, 0.01 ether);
    }}

    function test_underpaymentReverts() public {{
        vm.deal(alice, 1 ether);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector({name}.InsufficientPayment.selector, 0.009 ether, 0.01 ether));
        nft.mint{{value: 0.009 ether}}();
    }}

    function test_staleOracleBlocksPaidMint() public {{
        feed.set(2500e8, block.timestamp - 2 hours);
        vm.expectRevert();
        nft.mintPriceWei();
        feed.set(0, block.timestamp);
        vm.expectRevert();
        nft.mintPriceWei();
    }}

    /// Reads the live Chainlink ETH/USD feed on an Ethereum mainnet fork when MAINNET_RPC_URL is set.
    function test_fork_liveChainlinkPrice() public {{
        string memory rpc = vm.envOr("MAINNET_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {{ vm.skip(true); return; }}
        vm.createSelectFork(rpc);
        {name} live = new {name}({', '.join(a if a != 'address(feed)' else 'address(0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419)' for a in args).replace('1 hours', '1 days')});
        uint256 p = live.mintPriceWei();
        assertGt(p, 0.0005 ether); // $25 is more than 0.0005 ETH unless ETH > $50k
        assertLt(p, 1 ether);
    }}
""")
    if pause:
        g = "vm.prank(admin);"
        t.append(f"""
    function test_pauseBlocksTransfers() public {{
        vm.prank(admin);
        nft.mintTo(alice);
        {g}
        nft.pause();
        vm.prank(alice);
        vm.expectRevert();
        nft.transferFrom(alice, admin, 1);
        {g}
        nft.unpause();
        vm.prank(alice);
        nft.transferFrom(alice, admin, 1);
        assertEq(nft.ownerOf(1), admin);
    }}
""")
    t.append("}\n")
    return "".join(t)

def nft_deploy(name, roy, oracle):
    args = ["admin", 'vm.envOr("MAX_SUPPLY", uint256(1000))', 'vm.envOr("BASE_URI", string("ipfs://REPLACE_ME/"))']
    if oracle: args += ['vm.envAddress("PRICE_FEED") /* Sepolia ETH/USD: 0x694AA1769357215DE4FAC081bf1f309aDC325306 */', 'vm.envOr("MINT_PRICE_USD", uint256(25e18))', 'vm.envOr("MAX_PRICE_AGE", uint256(1 days))']
    if roy: args += ["admin", 'uint96(vm.envOr("ROYALTY_BPS", uint256(500)))']
    return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../src/{name}.sol";

/// PRICE_FEED=0x694AA1769357215DE4FAC081bf1f309aDC325306 forge script script/Deploy.s.sol --rpc-url $SEPOLIA_RPC_URL --account <keystore> --broadcast
contract Deploy is Script {{
    function run() external {{
        vm.startBroadcast();
        address admin = msg.sender;
        {name} c = new {name}(
            {(','+chr(10)+'            ').join(args)}
        );
        console2.log("{name}", address(c));
        vm.stopBroadcast();
    }}
}}
"""

ARCHETYPES = {"token": token, "nft": nft}
SUPPORTED = {"fungible-token", "token-permit", "governance", "access-control", "nft", "royalties", "price-oracle", "pausable"}

def choose(capids):
    if "nft" in capids or "royalties" in capids: return "nft"
    if capids & {"fungible-token", "token-permit", "governance"}: return "token"
    return None

# The exact component files each archetype's glue imports (slug, path) -> must be fetched from the forks.
def needed_components(arch, f):
    oz = "openzeppelin-contracts"; c = []
    if arch == "token":
        c.append((oz, "contracts/token/ERC20/ERC20.sol"))
        if "token-permit" in f or "governance" in f: c.append((oz, "contracts/token/ERC20/extensions/ERC20Permit.sol"))
        if "governance" in f:
            c += [(oz, "contracts/token/ERC20/extensions/ERC20Votes.sol"), (oz, "contracts/governance/Governor.sol"), (oz, "contracts/governance/TimelockController.sol"),
                  (oz, "contracts/governance/extensions/GovernorSettings.sol"), (oz, "contracts/governance/extensions/GovernorCountingSimple.sol"),
                  (oz, "contracts/governance/extensions/GovernorVotes.sol"), (oz, "contracts/governance/extensions/GovernorVotesQuorumFraction.sol"),
                  (oz, "contracts/governance/extensions/GovernorTimelockControl.sol"), (oz, "contracts/governance/IGovernor.sol"), (oz, "contracts/utils/Nonces.sol")]
        if "pausable" in f: c.append((oz, "contracts/token/ERC20/extensions/ERC20Pausable.sol"))
    else:
        c += [(oz, "contracts/token/ERC721/ERC721.sol"), (oz, "contracts/token/ERC721/IERC721.sol")]
        if "royalties" in f: c.append((oz, "contracts/token/common/ERC2981.sol"))
        if "pausable" in f: c.append((oz, "contracts/token/ERC721/extensions/ERC721Pausable.sol"))
        if "price-oracle" in f: c.append(("chainlink-evm", "contracts/src/v0.8/shared/interfaces/AggregatorV3Interface.sol"))
    if "access-control" in f or "governance" in f: c += [(oz, "contracts/access/AccessControl.sol"), (oz, "contracts/access/IAccessControl.sol")]
    else: c.append((oz, "contracts/access/Ownable.sol"))
    return c
