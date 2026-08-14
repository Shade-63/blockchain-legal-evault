const { expect } = require("chai");
const hre = require("hardhat");

describe("LegalEVaultRegistry", function () {
  let Registry;
  let registry;
  let owner;
  let addr1;

  // UUID bytes16 representation helper (slice to 16 bytes: 0x + 32 hex chars)
  const docId = hre.ethers.encodeBytes32String("doc-uuid").slice(0, 34);
  const versionIdA = hre.ethers.encodeBytes32String("version-a").slice(0, 34);
  const versionIdB = hre.ethers.encodeBytes32String("version-b").slice(0, 34);
  const dummyHashA = hre.ethers.keccak256(hre.ethers.toUtf8Bytes("content-a"));
  const dummyHashB = hre.ethers.keccak256(hre.ethers.toUtf8Bytes("content-b"));

  beforeEach(async function () {
    [owner, addr1] = await hre.ethers.getSigners();
    Registry = await hre.ethers.getContractFactory("LegalEVaultRegistry");
    registry = await Registry.deploy();
    await registry.waitForDeployment();
  });

  it("Should set the correct deployer as owner", async function () {
    expect(await registry.owner()).to.equal(owner.address);
  });

  it("Should allow the owner to register a document version successfully", async function () {
    const tx = await registry.registerVersion(versionIdA, docId, dummyHashA);
    const receipt = await tx.wait();

    // Verify mapping retrieval
    const record = await registry.registry(versionIdA);
    expect(record.isRegistered).to.be.true;
    expect(record.documentId).to.equal(docId);
    expect(record.versionId).to.equal(versionIdA);
    expect(record.sha256Hash).to.equal(dummyHashA);
    expect(record.registeredBy).to.equal(owner.address);

    // Verify event emission
    const filter = registry.filters.VersionRegistered();
    const events = await registry.queryFilter(filter, receipt.blockNumber);
    expect(events.length).to.equal(1);
    expect(events[0].args.versionId).to.equal(versionIdA);
    expect(events[0].args.documentId).to.equal(docId);
    expect(events[0].args.sha256Hash).to.equal(dummyHashA);
  });

  it("Should reject registration attempts from unauthorized wallets", async function () {
    await expect(
      registry.connect(addr1).registerVersion(versionIdA, docId, dummyHashA)
    ).to.be.revertedWith("Caller is not the authorized registrar");
  });

  it("Should reject duplicate registration of the same version ID", async function () {
    await registry.registerVersion(versionIdA, docId, dummyHashA);

    await expect(
      registry.registerVersion(versionIdA, docId, dummyHashB)
    ).to.be.revertedWith("Version already registered");
  });

  it("Should allow registering the same hash across different version IDs", async function () {
    await registry.registerVersion(versionIdA, docId, dummyHashA);

    // Same hash, different version ID B
    const tx = await registry.registerVersion(versionIdB, docId, dummyHashA);
    await tx.wait();

    const recordB = await registry.registry(versionIdB);
    expect(recordB.isRegistered).to.be.true;
    expect(recordB.sha256Hash).to.equal(dummyHashA);
  });
});
