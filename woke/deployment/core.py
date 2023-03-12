from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional, cast

import eth_utils

import woke.development.core
from woke.development.core import (
    Abi,
    Account,
    Address,
    RequestType,
    RevertToSnapshotFailedError,
    check_connected,
    fix_library_abi,
)
from woke.development.json_rpc.communicator import JsonRpcError, TxParams


class Chain(woke.development.core.Chain):
    @contextmanager
    def connect(
        self,
        uri: Optional[str] = None,
        *,
        accounts: Optional[int] = None,
        chain_id: Optional[int] = None,
        fork: Optional[str] = None,
        hardfork: Optional[str] = None,
        min_gas_price: Optional[int] = None,
        block_base_fee_per_gas: Optional[int] = None,
    ):
        yield from self._connect(
            uri,
            accounts=accounts,
            chain_id=chain_id,
            fork=fork,
            hardfork=hardfork,
            min_gas_price=min_gas_price,
            block_base_fee_per_gas=block_base_fee_per_gas,
        )

    def _connect_setup(self, min_gas_price: Optional[int]) -> None:
        self._require_signed_txs = True

        if min_gas_price is not None:
            try:
                self._chain_interface.set_min_gas_price(min_gas_price)
            except JsonRpcError:
                pass

    def _connect_finalize(self) -> None:
        pass

    def _update_nonce(self, address: Address, nonce: int) -> None:
        # nothing to do
        pass

    @check_connected
    def snapshot(self) -> str:
        snapshot_id = self._chain_interface.snapshot()

        self._snapshots[snapshot_id] = {
            "accounts": self._accounts.copy(),
            "default_call_account": self._default_call_account,
            "default_tx_account": self._default_tx_account,
            "txs": dict(self._txs),
            "blocks": dict(self._blocks._blocks),
        }
        return snapshot_id

    @check_connected
    def revert(self, snapshot_id: str) -> None:
        reverted = self._chain_interface.revert(snapshot_id)
        if not reverted:
            raise RevertToSnapshotFailedError()

        snapshot = self._snapshots[snapshot_id]
        self._accounts = snapshot["accounts"]
        self._default_call_account = snapshot["default_call_account"]
        self._default_tx_account = snapshot["default_tx_account"]
        self._txs = snapshot["txs"]
        self._blocks._blocks = snapshot["blocks"]
        del self._snapshots[snapshot_id]

    @property
    @check_connected
    def block_gas_limit(self) -> int:
        return self._blocks["pending"].gas_limit

    @block_gas_limit.setter
    @check_connected
    def block_gas_limit(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set block gas limit in deployment"
        )  # TODO do nothing instead?

    @property
    @check_connected
    def gas_price(self) -> int:
        return self.chain_interface.get_gas_price()

    @gas_price.setter
    @check_connected
    def gas_price(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set gas price in deployment"
        )  # TODO do nothing instead?

    @property
    @check_connected
    def max_priority_fee_per_gas(self) -> int:
        return self.chain_interface.get_max_priority_fee_per_gas()

    @max_priority_fee_per_gas.setter
    @check_connected
    def max_priority_fee_per_gas(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set max priority fee per gas in deployment"
        )  # TODO do nothing instead?

    def _build_transaction(
        self,
        request_type: RequestType,
        params: TxParams,
        arguments: Iterable,
        abi: Optional[Dict],
    ) -> TxParams:
        if "gasPrice" in params and (
            "maxFeePerGas" in params or "maxPriorityFeePerGas" in params
        ):
            raise ValueError(
                "Cannot specify both gas_price and max_fee_per_gas/max_priority_fee_per_gas"
            )
        if "maxFeePerGas" in params or "maxPriorityFeePerGas" in params:
            tx_type = 2
        elif "accessList" in params:
            tx_type = 1
        elif "gasPrice" in params:
            tx_type = 0
        else:
            tx_type = self._tx_type

        if "from" in params:
            sender = params["from"]
        else:
            if request_type == "call" and self.default_call_account is not None:
                sender = str(self.default_call_account.address)
            elif request_type == "tx" and self.default_tx_account is not None:
                sender = str(self.default_tx_account.address)
            else:
                raise ValueError(
                    "No from_ account specified and no default account set"
                )

        if "data" not in params:
            params["data"] = b""

        if abi is None:
            params["data"] += Abi.encode([], [])
        else:
            arguments = [self._convert_to_web3_type(arg) for arg in arguments]
            types = [
                eth_utils.abi.collapse_if_tuple(cast(Dict[str, Any], arg))
                for arg in fix_library_abi(abi["inputs"])
            ]
            params["data"] += Abi.encode(types, arguments)

        tx: TxParams = {
            "nonce": Account(sender, self).nonce,
            "from": sender,
            "value": params["value"] if "value" in params else 0,
            "data": params["data"],
        }
        if tx_type != 0:
            tx["type"] = tx_type

        if "to" in params:
            tx["to"] = params["to"]

        if tx_type == 0:
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self.gas_price
            )
        elif tx_type == 1:
            tx["accessList"] = params["accessList"] if "accessList" in params else []
            tx["chainId"] = self._chain_id
            tx["gasPrice"] = (
                params["gasPrice"] if "gasPrice" in params else self.gas_price
            )
        elif tx_type == 2:
            tx["accessList"] = params["accessList"] if "accessList" in params else []
            tx["chainId"] = self._chain_id
            tx["maxPriorityFeePerGas"] = (
                params["maxPriorityFeePerGas"]
                if "maxPriorityFeePerGas" in params
                else self.max_priority_fee_per_gas
            )
            if "maxFeePerGas" in params:
                tx["maxFeePerGas"] = params["maxFeePerGas"]
            else:
                if self.require_signed_txs:
                    tx["maxFeePerGas"] = tx["maxPriorityFeePerGas"] + int(
                        self.chain_interface.get_block("pending")["baseFeePerGas"], 16
                    )

        if "gas" not in params or params["gas"] == "auto":
            # use "auto when unset
            try:
                tx["gas"] = self._chain_interface.estimate_gas(tx)
            except JsonRpcError as e:
                self._process_call_revert(e)
                raise
        elif isinstance(params["gas"], int):
            tx["gas"] = params["gas"]
        else:
            raise ValueError(f"Invalid gas value: {params['gas']}")

        return tx


default_chain = Chain()