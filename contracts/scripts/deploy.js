const hre = require("hardhat");

async function main() {
  // Get contract factory
  const LegalEVaultRegistry = await hre.ethers.getContractFactory("LegalEVaultRegistry");
  
  // Deploy the contract
  const registry = await LegalEVaultRegistry.deploy();

  // Wait for the deployment transaction to be mined
  await registry.waitForDeployment();

  console.log(`LegalEVaultRegistry deployed to: ${await registry.getAddress()}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
