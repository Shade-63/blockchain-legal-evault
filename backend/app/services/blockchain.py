from web3 import Web3
from web3.middleware import geth_poa_middleware
from app.config import settings
import json
import threading
from typing import Optional, Dict
from pathlib import Path

# Thread lock to serialize blockchain transaction signing and avoid nonce collisions
_tx_lock = threading.Lock()

class BlockchainAdapter:
    """
    EVM Blockchain Adapter Service.
    Wraps JSON-RPC interactions, transaction signing, and verification.
    """
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.blockchain_rpc_url))
        
        # Inject POA middleware for compatibility with local Hardhat/Geth PoA chains
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Load ABI
        abi_path = Path(__file__).resolve().parent.parent / "abi" / "LegalEVaultRegistry.json"
        with open(abi_path, "r") as f:
            artifact = json.load(f)
            if isinstance(artifact, dict) and "abi" in artifact:
                self.abi = artifact["abi"]
            else:
                self.abi = artifact
            
        self.contract_address = Web3.to_checksum_address(settings.contract_address)
        self.contract = self.w3.eth.contract(address=self.contract_address, abi=self.abi)
        
        # Derived registrar wallet address from private key
        self.private_key = settings.blockchain_private_key
        try:
            self.account = self.w3.eth.account.from_key(self.private_key)
            self.registrar_address = self.account.address
        except Exception as e:
            self.account = None
            self.registrar_address = None

    def startup_validation(self):
        """
        Runs on API startup. Verifies chain connectivity, contract bytecode,
        and confirms that the configured backend registry wallet is the contract owner.
        Fails startup if checks do not pass.
        """
        # 1. Connection check
        if not self.w3.is_connected():
            raise RuntimeError(f"Blockchain RPC connection failed: unable to connect to {settings.blockchain_rpc_url}")
            
        # 2. Bytecode check
        bytecode = self.w3.eth.get_code(self.contract_address)
        if len(bytecode) <= 2:  # '0x' or empty bytes
            raise ValueError(f"Contract bytecode not found at address: {self.contract_address}. Make sure it is deployed.")

        # 3. Ownership validation
        if not self.registrar_address:
            raise ValueError("Invalid BLOCKCHAIN_PRIVATE_KEY configuration.")

        contract_owner = self.contract.functions.owner().call()
        if self.registrar_address.lower() != contract_owner.lower():
            raise ValueError(
                f"Configuration Mismatch: Configured backend registry wallet ({self.registrar_address}) "
                f"does not match contract owner ({contract_owner})."
            )

    def get_registration(self, version_id_bytes: bytes) -> Optional[dict]:
        """
        Queries contract registry mapping by 16-byte version ID.
        Returns VersionRecord dict if isRegistered == True, else None.
        """
        if len(version_id_bytes) != 16:
            raise ValueError("version_id must be exactly 16 bytes.")

        record = self.contract.functions.registry(version_id_bytes).call()
        
        # record return shape: [documentId, versionId, sha256Hash, blockNumber, timestamp, registeredBy, isRegistered]
        is_registered = record[6]
        if not is_registered:
            return None
            
        return {
            "document_id": record[0],
            "version_id": record[1],
            "sha256_hash": record[2].hex(),
            "block_number": record[3],
            "timestamp": record[4],
            "registered_by": record[5],
            "is_registered": record[6]
        }

    def register_version(self, version_id_bytes: bytes, document_id_bytes: bytes, sha256_hash_bytes: bytes) -> str:
        """
        Signs and broadcasts registerVersion transaction from the backend registry wallet.
        Uses in-memory serialization lock to prevent nonce conflicts.
        Returns the transaction hash.
        """
        if len(version_id_bytes) != 16 or len(document_id_bytes) != 16:
            raise ValueError("IDs must be exactly 16 bytes.")
        if len(sha256_hash_bytes) != 32:
            raise ValueError("SHA-256 hash must be exactly 32 bytes.")

        # Serialize transactions using in-memory lock
        with _tx_lock:
            nonce = self.w3.eth.get_transaction_count(self.registrar_address, "pending")
            
            # Build transaction
            tx = self.contract.functions.registerVersion(
                version_id_bytes,
                document_id_bytes,
                sha256_hash_bytes
            ).build_transaction({
                "chainId": self.w3.eth.chain_id,
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": nonce
            })

            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return self.w3.to_hex(tx_hash)

    def verify_transaction_status(self, tx_hash: str) -> Optional[dict]:
        """
        Checks transaction status.
        If mined successfully, returns block number and block timestamp.
        If reverted or not mined yet, returns None.
        """
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt.status == 1:
                block = self.w3.eth.get_block(receipt.blockNumber)
                return {
                    "block_number": receipt.blockNumber,
                    "timestamp": block.timestamp
                }
            return None
        except Exception:
            return None

    def grant_permission(self, version_id_bytes: bytes, commitment_hash_bytes: bytes) -> str:
        """
        Signs and broadcasts grantPermission transaction from the backend registry wallet.
        Uses in-memory serialization lock to prevent nonce conflicts.
        """
        if len(version_id_bytes) != 16:
            raise ValueError("version_id must be exactly 16 bytes.")
        if len(commitment_hash_bytes) != 32:
            raise ValueError("commitment_hash must be exactly 32 bytes.")

        with _tx_lock:
            nonce = self.w3.eth.get_transaction_count(self.registrar_address, "pending")
            tx = self.contract.functions.grantPermission(
                version_id_bytes,
                commitment_hash_bytes
            ).build_transaction({
                "chainId": self.w3.eth.chain_id,
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": nonce
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return self.w3.to_hex(tx_hash)

    def revoke_permission(self, version_id_bytes: bytes, commitment_hash_bytes: bytes) -> str:
        """
        Signs and broadcasts revokePermission transaction from the backend registry wallet.
        Uses in-memory serialization lock to prevent nonce conflicts.
        """
        if len(version_id_bytes) != 16:
            raise ValueError("version_id must be exactly 16 bytes.")
        if len(commitment_hash_bytes) != 32:
            raise ValueError("commitment_hash must be exactly 32 bytes.")

        with _tx_lock:
            nonce = self.w3.eth.get_transaction_count(self.registrar_address, "pending")
            tx = self.contract.functions.revokePermission(
                version_id_bytes,
                commitment_hash_bytes
            ).build_transaction({
                "chainId": self.w3.eth.chain_id,
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": nonce
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return self.w3.to_hex(tx_hash)

    def is_permission_active(self, version_id_bytes: bytes, commitment_hash_bytes: bytes) -> bool:
        """
        Queries contract registry to check if permission commitment is active on-chain.
        """
        if len(version_id_bytes) != 16:
            raise ValueError("version_id must be exactly 16 bytes.")
        if len(commitment_hash_bytes) != 32:
            raise ValueError("commitment_hash must be exactly 32 bytes.")

        return self.contract.functions.isPermissionActive(version_id_bytes, commitment_hash_bytes).call()

