package main

import (
	"context"
	"crypto/ecdsa"
	"encoding/hex"
	"flag"
	"fmt"
	"log"
	"math/big"
	"os"
	"time"

	"github.com/ethereum/go-ethereum/accounts/abi/bind"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/ethclient"
	"github.com/joho/godotenv"
	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/core/types"
)

const (
	BALANCE_THRESHOLD = 0.001
	GAS_LIMIT         = 56000
)

func main() {
	gasPriceGwei := flag.Int("gas_price_gwei", 60, "Set the gas price in GWEI.")
	attempts := flag.Int("attempts", 1, "Number of attempts to play.")
	interval := flag.Int("interval", 5, "Delay between attempts in seconds.")
	flag.Parse()

	err := godotenv.Load("settings.env")
	if err != nil {
		log.Fatalf("Error loading .env file")
	}

	rpcURL := os.Getenv("RPC_URL")
	privateKeyHex := os.Getenv("PRIVATE_KEY")
	contractAddress := os.Getenv("FRONTRUNNER_CONTRACT_ADDRESS")

	client, err := ethclient.Dial(rpcURL)
	if err != nil {
		log.Fatalf("Failed to connect to Ethereum network: %v", err)
	}
	fmt.Println("Connected to the Monad network.")

	privateKeyBytes, err := hex.DecodeString(privateKeyHex)
	if err != nil {
		log.Fatalf("Invalid private key: %v", err)
	}

	privateKey, err := crypto.ToECDSA(privateKeyBytes)
	if err != nil {
		log.Fatalf("Failed to parse private key: %v", err)
	}

	publicKey := privateKey.Public().(*ecdsa.PublicKey)
	fromAddress := crypto.PubkeyToAddress(*publicKey)
	fmt.Printf("Using account: %s\n", fromAddress.Hex())

	balance, err := client.BalanceAt(context.Background(), fromAddress, nil)
	if err != nil {
		log.Fatalf("Failed to get account balance: %v", err)
	}

	fmt.Printf("Account balance: %f ETH\n", new(big.Float).Quo(new(big.Float).SetInt(balance), big.NewFloat(1e18)))

	if balance.Cmp(big.NewInt(int64(BALANCE_THRESHOLD*1e18))) < 0 {
		log.Println("Account balance is too low to play. Please add funds.")
		return
	}

	contractAddr := common.HexToAddress(contractAddress)
	gasPrice := big.NewInt(int64(*gasPriceGwei * 1e9))

	nonce, err := client.PendingNonceAt(context.Background(), fromAddress)
	if err != nil {
		log.Fatalf("Failed to get nonce: %v", err)
	}

	fmt.Printf("Nonce: %d\n", nonce)

	for *attempts > 0 {
		tx := types.NewTransaction(nonce, contractAddr, big.NewInt(0), GAS_LIMIT, gasPrice, nil)
		signedTx, err := types.SignTx(tx, types.NewEIP155Signer(big.NewInt(1)), privateKey)
		if err != nil {
			log.Fatalf("Failed to sign transaction: %v", err)
		}

		err = client.SendTransaction(context.Background(), signedTx)
		if err != nil {
			log.Printf("Failed to send transaction: %v", err)
		} else {
			fmt.Printf("Sent transaction with nonce %d. Tx hash: %s\n", nonce, signedTx.Hash().Hex())
		}

		nonce++
		time.Sleep(time.Duration(*interval) * time.Second)
		*attempts--
	}
	log.Println("All attempts completed. Exiting...")
}
