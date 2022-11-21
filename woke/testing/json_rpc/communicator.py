import asyncio
import enum
import json
import logging
from typing import Any, Dict, List, Optional, Union

import aiohttp
from aiohttp import ClientSession
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


class BlockEnum(str, enum.Enum):
    EARLIEST = "earliest"
    FINALIZED = "finalized"
    SAFE = "safe"
    LATEST = "latest"
    PENDING = "pending"


TxParams = TypedDict(
    "TxParams",
    {
        "type": int,
        "nonce": int,
        "to": str,
        "from": str,
        "gas": int,
        "value": int,
        "data": bytes,
        "gas_price": int,
        "max_priority_fee_per_gas": int,
        "max_fee_per_gas": int,
        "access_list": List,
        "chain_id": int,
    },
    total=False,
)


class JsonRpcError(Exception):
    def __init__(self, data: Dict):
        self.data = data


class JsonRpcCommunicator:
    __client_session: ClientSession
    __port: int
    __request_id: int
    __url: str

    def __init__(self, uri: str, client_session: ClientSession):
        self.__client_session = client_session
        self.__request_id = 0
        self.__url = uri

    async def _send_request(
        self, method_name: str, params: Optional[List] = None
    ) -> str:
        post_data = {
            "jsonrpc": "2.0",
            "method": method_name,
            "params": params if params is not None else [],
            "id": self.__request_id,
        }
        logger.info(f"Sending request:\n{post_data}")
        self.__request_id += 1

        async with self.__client_session.post(self.__url, json=post_data) as response:
            text = await response.text()
            logger.info(f"Received response:\n{text}")
            return text

    def _process_response(self, text: str) -> Any:
        response = json.loads(text)
        if "error" in response:
            raise JsonRpcError(response["error"])
        return response["result"]

    @staticmethod
    def _encode_transaction(transaction: TxParams) -> Dict:
        tx = {}
        if "type" in transaction:
            tx["type"] = hex(transaction["type"])
        if "nonce" in transaction:
            tx["nonce"] = hex(transaction["nonce"])
        if "to" in transaction:
            tx["to"] = transaction["to"]
        if "from" in transaction:
            tx["from"] = transaction["from"]
        if "gas" in transaction:
            tx["gas"] = hex(transaction["gas"])
        if "value" in transaction:
            tx["value"] = hex(transaction["value"])
        if "data" in transaction:
            tx["data"] = "0x" + transaction["data"].hex()
        if "gas_price" in transaction:
            tx["gasPrice"] = hex(transaction["gas_price"])
        if "max_priority_fee_per_gas" in transaction:
            tx["maxPriorityFeePerGas"] = hex(transaction["max_priority_fee_per_gas"])
        if "max_fee_per_gas" in transaction:
            tx["maxFeePerGas"] = hex(transaction["max_fee_per_gas"])
        if "access_list" in transaction:
            tx["accessList"] = transaction["access_list"]
        if "chain_id" in transaction:
            tx["chainId"] = hex(transaction["chain_id"])
        return tx

    async def eth_get_block_by_number(
        self, block: Union[int, str], include_transactions: bool
    ) -> Dict:
        """Returns information about a block by block number."""
        if isinstance(block, int):
            params = [hex(block), include_transactions]
        elif isinstance(block, str):
            params = [block, include_transactions]
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = await self._send_request("eth_getBlockByNumber", params)
        return self._process_response(text)

    async def eth_block_number(self) -> int:
        """Returns the number of most recent block."""
        text = await self._send_request("eth_blockNumber")
        return int(self._process_response(text), 16)

    async def eth_chain_id(self) -> int:
        """Returns the chain ID of the current network."""
        text = await self._send_request("eth_chainId")
        return int(self._process_response(text), 16)

    async def eth_accounts(self) -> List[str]:
        """Returns a list of addresses owned by client."""
        text = await self._send_request("eth_accounts")
        return self._process_response(text)

    async def eth_call(
        self,
        transaction: TxParams,
        block: Union[int, str] = BlockEnum.LATEST,
    ) -> bytes:
        """Executes a new message call immediately without creating a transaction on the block chain."""
        params: List[Any] = [self._encode_transaction(transaction)]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = await self._send_request("eth_call", params)
        return bytes.fromhex(self._process_response(text)[2:])

    async def eth_estimate_gas(
        self, transaction: TxParams, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Generates and returns an estimate of how much gas is necessary to allow the transaction to complete."""
        params: List[Any] = [self._encode_transaction(transaction)]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = await self._send_request("eth_estimateGas", params)
        return int(self._process_response(text), 16)

    async def eth_gas_price(self) -> int:
        """Returns the current price per gas in wei."""
        text = await self._send_request("eth_gasPrice")
        return int(self._process_response(text), 16)

    async def eth_get_balance(
        self, address: str, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Returns the balance of the account of given address."""
        params = [address]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = await self._send_request("eth_getBalance", params)
        return int(self._process_response(text), 16)

    async def eth_get_transaction_count(
        self, address: str, block: Union[int, str] = BlockEnum.LATEST
    ) -> int:
        """Returns the number of transactions sent from an address."""
        params = [address]
        if isinstance(block, int):
            params.append(hex(block))
        elif isinstance(block, str):
            params.append(block)
        else:
            raise TypeError("block must be either int or BlockEnum")
        text = await self._send_request("eth_getTransactionCount", params)
        return int(self._process_response(text), 16)

    async def eth_send_transaction(self, transaction: TxParams) -> str:
        """Signs and submits a transaction."""
        text = await self._send_request(
            "eth_sendTransaction", [self._encode_transaction(transaction)]
        )
        return self._process_response(text)

    async def eth_get_transaction_receipt(self, tx_hash: str) -> Dict:
        """Returns the receipt of a transaction by transaction hash."""
        text = await self._send_request("eth_getTransactionReceipt", [tx_hash])
        return self._process_response(text)

    async def hardhat_set_balance(self, address: str, balance: int) -> None:
        """Sets the balance of the account of given address."""
        params = [address, hex(balance)]
        text = await self._send_request("hardhat_setBalance", params)
        _ = self._process_response(text)

    async def hardhat_impersonate_account(self, address: str) -> None:
        """Impersonates an account."""
        params = [address]
        text = await self._send_request("hardhat_impersonateAccount", params)
        _ = self._process_response(text)

    async def hardhat_stop_impersonating_account(self, address: str) -> None:
        """Stops impersonating an account."""
        params = [address]
        text = await self._send_request("hardhat_stopImpersonatingAccount", params)
        _ = self._process_response(text)

    async def hardhat_reset(self, options: Optional[Dict] = None) -> None:
        text = await self._send_request(
            "hardhat_reset", [options] if options is not None else []
        )
        _ = self._process_response(text)

    async def anvil_set_balance(self, address: str, balance: int) -> None:
        params = [address, hex(balance)]
        text = await self._send_request("anvil_setBalance", params)
        _ = self._process_response(text)

    async def anvil_impersonate_account(self, address: str) -> None:
        params = [address]
        text = await self._send_request("anvil_impersonateAccount", params)
        _ = self._process_response(text)

    async def anvil_stop_impersonating_account(self, address: str) -> None:
        params = [address]
        text = await self._send_request("anvil_stopImpersonatingAccount", params)
        _ = self._process_response(text)

    async def anvil_reset(self, options: Optional[Dict] = None) -> None:
        text = await self._send_request(
            "anvil_reset", [options] if options is not None else []
        )
        _ = self._process_response(text)

    async def evm_set_account_balance(self, address: str, balance: int) -> None:
        """Sets the given account's balance to the specified WEI value. Mines a new block before returning."""
        params = [address, hex(balance)]
        text = await self._send_request("evm_setAccountBalance", params)
        _ = self._process_response(text)

    async def evm_set_block_gas_limit(self, gas_limit: int) -> None:
        params = [hex(gas_limit)]
        text = await self._send_request("evm_setBlockGasLimit", params)
        _ = self._process_response(text)

    async def evm_add_account(self, address: str, passphrase: str) -> bool:
        params = [address, passphrase]
        text = await self._send_request("evm_addAccount", params)
        return self._process_response(text)

    async def evm_snapshot(self) -> str:
        text = await self._send_request("evm_snapshot")
        return self._process_response(text)

    async def evm_revert(self, snapshot_id: str) -> bool:
        text = await self._send_request("evm_revert", [snapshot_id])
        return self._process_response(text)

    async def web3_client_version(self) -> str:
        """Returns the current client version."""
        text = await self._send_request("web3_clientVersion")
        return self._process_response(text)

    async def debug_trace_transaction(
        self, tx_hash: str, options: Optional[Dict] = None
    ) -> Dict:
        """Get debug traces of already-minted transactions."""
        params: List[Any] = [tx_hash]
        if options is not None:
            params.append(options)
        text = await self._send_request("debug_traceTransaction", params)
        return self._process_response(text)

    async def trace_transaction(self, tx_hash: str) -> Dict:
        text = await self._send_request("trace_transaction", [tx_hash])
        return self._process_response(text)

    async def personal_unlock_account(
        self, address: str, passphrase: str, duration: int
    ) -> bool:
        params = [address, passphrase, hex(duration)]
        text = await self._send_request("personal_unlockAccount", params)
        return self._process_response(text)
