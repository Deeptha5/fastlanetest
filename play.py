import logging
import argparse
import toml
import time
import random
from web3 import Web3

from src.settings.settings import Settings, ApiSettings, GameSettings, EOA
from src.logger.logger import Logs

BALANCE_THRESHOLD: float = 0.001
GAS_LIMIT: int = 53000

def get_dynamic_gas_price(w3, base_price):
    """Adjust gas price dynamically based on network conditions."""
    network_gas_price = w3.eth.gas_price
    return max(int(network_gas_price * 1.1), base_price)

def play() -> None:
    parser = argparse.ArgumentParser(description="Break Monad Frontrunner Bot.")
    parser.add_argument('--gas_price_gwei', type=int, default=0, help="Set the gas price in GWEI.")
    parser.add_argument('--attempts', type=int, default=10000000, help="Number of attempts to play.")
    parser.add_argument('--interval', type=float, default=1, help="Delay between attempts in seconds.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    logger = Logs(__name__).log(level=logging.INFO)

    config_file = toml.load('settings.toml')
    settings = Settings(
        api_settings=ApiSettings(**config_file['api_settings']),
        game_settings=GameSettings(**config_file['game_settings']),
        eoa=EOA(**config_file['eoa'])
    )

    w3 = Web3(Web3.HTTPProvider(settings.api_settings.rpc_url))
    if not w3.is_connected():
        raise Exception("Failed to connect to the Ethereum network.")
    logger.info("Connected to the Monad network.")

    contract = w3.eth.contract(
        address=w3.to_checksum_address(settings.game_settings.frontrunner_contract_address),
        abi=settings.game_settings.abi
    )

    base_gas_price = int(w3.eth.gas_price * 10**-9) if args.gas_price_gwei == 0 else int(args.gas_price_gwei)
    logger.info(f"Base gas price: {base_gas_price} GWEI")

    try:
        account = w3.eth.account.from_key(settings.eoa.private_key)
    except Exception as e:
        logger.error(f"Failed to get account from private key: {e}")
        return
    logger.info(f"Account: {account.address}")

    balance = w3.from_wei(w3.eth.get_balance(account.address), 'ether')
    logger.info(f"Account balance: {balance} Testnet Monad")
    if balance < BALANCE_THRESHOLD:
        logger.error("Balance too low! Exiting...")
        return

    try:
        wins, losses = contract.functions.getScore(account.address).call()
        logger.info(f"Current Score: {wins} Wins, {losses} Losses")
    except Exception as e:
        logger.error(f"Failed to get score: {e}")
        return

    nonce = w3.eth.get_transaction_count(account.address)
    chain_id = w3.eth.chain_id
    attempts = args.attempts

    while attempts > 0:
        gas_price_wei = get_dynamic_gas_price(w3, base_gas_price)
        logger.info(f"Using Gas Price: {gas_price_wei // 10**9} GWEI")
        
        try:
            txn = contract.functions.frontrun().build_transaction({
                'chainId': chain_id,
                'gas': GAS_LIMIT,
                'gasPrice': gas_price_wei,
                'nonce': nonce,
            })
            signed_txn = account.sign_transaction(txn)
            tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            logger.info(f"Sent transaction {tx_hash.hex()} with nonce {nonce}")
        except ValueError as e:
            logger.error(f"Transaction failed (ValueError): {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        
        nonce += 1
        attempts -= 1
        time.sleep(random.uniform(args.interval * 0.8, args.interval * 1.2))
    
    logger.info("Attempts completed. Exiting...")

if __name__ == "__main__":
    play()
