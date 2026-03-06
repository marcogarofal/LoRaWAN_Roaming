#!/usr/bin/env python3
"""
Auto-deploy script for LoRaWAN Blockchain System

This script automatically deploys and configures:
- Catalog Smart Contract
- Vodafone Provider Smart Contract (Forwarder)
- Tim Provider Smart Contract (Home)

Usage:
    python3 auto_deploy.py --config config_deploy.yaml
"""

import argparse
import json
import subprocess
import sys
import os
import yaml
from pathlib import Path

# Add blockchain scripts path
PYTHON_SCRIPTS_PATH = os.path.expanduser('./smart_contract/')
sys.path.insert(0, PYTHON_SCRIPTS_PATH)

try:
    import beaker as bk
    import _SC as sla
    import _catalogo as ct
    from algosdk import account, atomic_transaction_composer, transaction
    print(f"✅ Imported Smart Contract modules from: {PYTHON_SCRIPTS_PATH}")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)

PAYMENT_AMT = 1000000  # 1 ALGO

class Color:
    """ANSI color codes"""
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{text:^70}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}\n")

def print_success(text):
    print(f"{Color.GREEN}✅ {text}{Color.END}")

def print_info(text):
    print(f"{Color.BLUE}ℹ️  {text}{Color.END}")

def print_warning(text):
    print(f"{Color.YELLOW}⚠️  {text}{Color.END}")

def print_error(text):
    print(f"{Color.RED}❌ {text}{Color.END}")

def run_algokit_command(command):
    """Run algokit command and return output"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {command}")
        print_error(f"Error: {e.stderr}")
        return None

def get_account_list():
    """Get list of accounts with their app IDs"""
    output = run_algokit_command("algokit goal account list")
    if not output:
        return []

    accounts = []
    for line in output.split('\n'):
        if '[online]' in line:
            parts = line.split()
            address = parts[1]

            # Extract app IDs if present
            app_ids = []
            if 'created app IDs:' in line:
                ids_part = line.split('created app IDs:')[1].strip().rstrip(']')
                if ids_part:
                    app_ids = [int(x.strip()) for x in ids_part.split(',')]

            accounts.append({
                'address': address,
                'app_ids': app_ids
            })

    return accounts

def export_account_mnemonic(address):
    """Export mnemonic for an account"""
    print_info(f"Exporting mnemonic for {address[:8]}...")
    output = run_algokit_command(f"algokit goal account export -a {address}")

    if output and "Exported key for account" in output:
        # Extract mnemonic from output
        lines = output.split('\n')
        for line in lines:
            if len(line.split()) >= 24:  # Mnemonic has 25 words
                return line.strip()

    return None

def deploy_catalog(algod_client, lora_account):
    """Deploy catalog Smart Contract"""
    print_header("📚 DEPLOYING CATALOG SMART CONTRACT")

    app_client_catalog = bk.client.ApplicationClient(
        client=algod_client,
        app=ct.app,
        sender=lora_account.address,
        signer=lora_account.signer,
    )

    print_info("Creating catalog application...")
    app_id_catalog, address_catalog, txid_catalog = app_client_catalog.create()

    print_success(f"Catalog deployed!")
    print(f"   App ID: {app_id_catalog}")
    print(f"   Address: {address_catalog}")
    print(f"   TxID: {txid_catalog}")

    return app_id_catalog, app_client_catalog

def deploy_provider_sc(algod_client, provider_account, provider_name):
    """Deploy provider Smart Contract"""
    print_header(f"🏢 DEPLOYING {provider_name.upper()} SMART CONTRACT")

    app_client_sc = bk.client.ApplicationClient(
        client=algod_client,
        app=sla.app,
        sender=provider_account.address,
        signer=provider_account.signer,
    )

    print_info(f"Creating {provider_name} Smart Contract...")
    app_id_sc, address_sc, txid_sc = app_client_sc.create()

    print_success(f"{provider_name} SC deployed!")
    print(f"   App ID: {app_id_sc}")
    print(f"   Address: {address_sc}")
    print(f"   TxID: {txid_sc}")

    # Fund the Smart Contract
    print_info("Funding Smart Contract...")
    app_client_sc.fund(10 * bk.consts.algo)
    print_success("Smart Contract funded with 10 ALGO")

    return app_id_sc, app_client_sc

def initialize_sc(app_client_sc, config):
    """Initialize Smart Contract with parameters"""
    print_info("Initializing Smart Contract...")

    result = app_client_sc.call(
        sla.init,
        app_id_catalog=config['catalog_app_id'],
        price=config['price'],
        threshold=config['threshold'],
        tolerance=config['tolerance'],
        payment_tolerance=config.get('payment_tolerance', 95),
        token=config['token'],
        gwid=config['gwid'],
    )

    print_success(f"Smart Contract initialized: {result.return_value}")
    print(f"   Token: {config['token']}")
    print(f"   Gateway ID: {config['gwid']}")
    print(f"   Price: {config['price']} mALGO")
    print(f"   Threshold: {config['threshold']} packets")

def opt_in_to_catalog(algod_client, app_client_sc, provider_account, catalog_app_id):
    """Opt-in provider to catalog"""
    print_info("Opting in to catalog...")

    app_client_catalog = bk.client.ApplicationClient(
        client=algod_client,
        app=ct.app,
        app_id=catalog_app_id,
        sender=provider_account.address,
        signer=provider_account.signer,
    )

    # Get catalog creator address
    catalog_info = algod_client.application_info(catalog_app_id)
    catalog_creator = catalog_info["params"]["creator"]

    # Create payment transaction
    sp = algod_client.suggested_params()
    ptxn = atomic_transaction_composer.TransactionWithSigner(
        txn=transaction.PaymentTxn(
            sender=provider_account.address,
            sp=sp,
            receiver=catalog_creator,
            amt=PAYMENT_AMT
        ),
        signer=provider_account.signer
    )

    try:
        app_client_catalog.opt_in(payment=ptxn)
        print_success("Opted in to catalog")
    except Exception as e:
        if "already opted in" in str(e).lower():
            print_warning("Already opted in to catalog")
        else:
            raise

def register_in_catalog(algod_client, provider_account, catalog_app_id, netid, name, sc_app_id):
    """Register provider in catalog"""
    print_info(f"Registering {name} in catalog...")

    app_client_catalog = bk.client.ApplicationClient(
        client=algod_client,
        app=ct.app,
        app_id=catalog_app_id,
        sender=provider_account.address,
        signer=provider_account.signer,
    )

    result = app_client_catalog.call(
        ct.set_entry_provider,
        NetID_Provider=netid,
        Name_Provider=name,
        app_id_SC_Provider=sc_app_id,
    )

    print_success(f"Registered in catalog: {result.return_value}")
    print(f"   NetID: {netid}")
    print(f"   Name: {name}")
    print(f"   Endpoint SC: {sc_app_id}")

def verify_catalog(algod_client, catalog_app_id):
    """Verify catalog contents"""
    print_header("📋 CATALOG VERIFICATION")

    indexer_client = bk.localnet.get_indexer_client()
    response = indexer_client.accounts(application_id=catalog_app_id)

    import base64
    from prettytable import PrettyTable

    table = PrettyTable()
    table.field_names = ["Address", "NetID", "Provider", "SC App ID"]

    for account_data in response['accounts']:
        address = account_data['address']

        if 'apps-local-state' in account_data:
            for app_state in account_data['apps-local-state']:
                if app_state.get('id') == catalog_app_id:
                    kv = app_state.get('key-value', [])

                    netid = ""
                    name = ""
                    endpoint = 0

                    for item in kv:
                        key = base64.b64decode(item['key']).decode('utf-8')

                        if key == 'NetID':
                            netid = base64.b64decode(item['value']['bytes']).decode('utf-8')
                        elif key == 'Provider Name':
                            name = base64.b64decode(item['value']['bytes']).decode('utf-8')
                        elif key == 'Endpoint of Smart Contract':
                            endpoint = item['value']['uint']

                    if netid and name and endpoint:
                        table.add_row([address[:8]+"...", netid, name, endpoint])

    print(table)

def save_deployment_info(config_file, deployment_data):
    """Save deployment information to file"""
    output_file = config_file.replace('.yaml', '_deployed.json')

    with open(output_file, 'w') as f:
        json.dump(deployment_data, f, indent=2)

    print_success(f"Deployment info saved to: {output_file}")
    return output_file

def main():
    parser = argparse.ArgumentParser(description='Auto-deploy LoRaWAN Blockchain System')
    parser.add_argument('--config', required=True, help='Configuration YAML file')
    parser.add_argument('--skip-catalog', action='store_true', help='Skip catalog deployment')
    args = parser.parse_args()

    # Load configuration
    print_header("📖 LOADING CONFIGURATION")
    with open(args.config) as f:
        config = yaml.safe_load(f)

    print_info(f"Loaded config: {args.config}")
    print(json.dumps(config, indent=2))

    # Setup Algorand clients
    print_header("🔗 CONNECTING TO ALGORAND")
    algod_client = bk.localnet.get_algod_client()

    # Get accounts
    accounts = bk.localnet.kmd.get_accounts()

    lora_account = bk.localnet.LocalAccount(
        address=accounts[0].address,
        private_key=accounts[0].private_key
    )
    vodafone_account = bk.localnet.LocalAccount(
        address=accounts[2].address,
        private_key=accounts[2].private_key
    )
    tim_account = bk.localnet.LocalAccount(
        address=accounts[1].address,
        private_key=accounts[1].private_key
    )

    print_success(f"LoRa (Catalog): {lora_account.address}")
    print_success(f"Vodafone: {vodafone_account.address}")
    print_success(f"Tim: {tim_account.address}")

    deployment_data = {
        'catalog': {},
        'vodafone': {},
        'tim': {}
    }

    # Deploy Catalog
    if not args.skip_catalog:
        catalog_app_id, _ = deploy_catalog(algod_client, lora_account)
        deployment_data['catalog']['app_id'] = catalog_app_id
        deployment_data['catalog']['address'] = lora_account.address
    else:
        catalog_app_id = config.get('catalog_app_id')
        if not catalog_app_id:
            print_error("--skip-catalog requires catalog_app_id in config")
            sys.exit(1)
        print_info(f"Using existing catalog: {catalog_app_id}")

    # Deploy Vodafone SC
    vodafone_app_id, vodafone_client = deploy_provider_sc(
        algod_client, vodafone_account, "Vodafone"
    )
    deployment_data['vodafone']['app_id'] = vodafone_app_id
    deployment_data['vodafone']['address'] = vodafone_account.address

    # Initialize Vodafone SC
    vodafone_config = config['providers']['vodafone']
    vodafone_config['catalog_app_id'] = catalog_app_id
    initialize_sc(vodafone_client, vodafone_config)

    # Vodafone: Opt-in and Register
    opt_in_to_catalog(algod_client, vodafone_client, vodafone_account, catalog_app_id)
    register_in_catalog(
        algod_client, vodafone_account, catalog_app_id,
        vodafone_config['netid'],
        vodafone_config['name'],
        vodafone_app_id
    )

    deployment_data['vodafone'].update({
        'netid': vodafone_config['netid'],
        'name': vodafone_config['name'],
        'token': vodafone_config['token'],
        'gwid': vodafone_config['gwid'],
    })

    # Deploy Tim SC
    tim_app_id, tim_client = deploy_provider_sc(
        algod_client, tim_account, "Tim"
    )
    deployment_data['tim']['app_id'] = tim_app_id
    deployment_data['tim']['address'] = tim_account.address

    # Initialize Tim SC
    tim_config = config['providers']['tim']
    tim_config['catalog_app_id'] = catalog_app_id
    initialize_sc(tim_client, tim_config)

    # Tim: Opt-in and Register
    opt_in_to_catalog(algod_client, tim_client, tim_account, catalog_app_id)
    register_in_catalog(
        algod_client, tim_account, catalog_app_id,
        tim_config['netid'],
        tim_config['name'],
        tim_app_id
    )

    deployment_data['tim'].update({
        'netid': tim_config['netid'],
        'name': tim_config['name'],
        'token': tim_config['token'],
        'gwid': tim_config['gwid'],
    })

    # Verify catalog
    verify_catalog(algod_client, catalog_app_id)

    # Export mnemonics
    print_header("🔑 EXPORTING MNEMONICS")

    vodafone_mnemonic = export_account_mnemonic(vodafone_account.address)
    if vodafone_mnemonic:
        deployment_data['vodafone']['mnemonic'] = vodafone_mnemonic
        print_success(f"Vodafone mnemonic exported")

    tim_mnemonic = export_account_mnemonic(tim_account.address)
    if tim_mnemonic:
        deployment_data['tim']['mnemonic'] = tim_mnemonic
        print_success(f"Tim mnemonic exported")

    # Save deployment info
    print_header("💾 SAVING DEPLOYMENT INFO")
    output_file = save_deployment_info(args.config, deployment_data)

    # Print summary
    print_header("🎉 DEPLOYMENT COMPLETE!")
    print(f"\n{Color.BOLD}Catalog App ID:{Color.END} {catalog_app_id}")
    print(f"{Color.BOLD}Vodafone SC App ID:{Color.END} {vodafone_app_id}")
    print(f"{Color.BOLD}Tim SC App ID:{Color.END} {tim_app_id}")

    print(f"\n{Color.BOLD}Next steps:{Color.END}")
    print(f"1. Use the deployment info in: {output_file}")
    print(f"2. Initialize blockchain_service.py with Vodafone config")
    print(f"3. Configure Gateway Bridge")

    print(f"\n{Color.GREEN}✅ All Smart Contracts deployed and configured!{Color.END}\n")

if __name__ == '__main__':
    main()
