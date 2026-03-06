#deploy_catalogo_by_LoRa.py

from beaker.client.api_providers import AlgoNode, Network
from algosdk import account, encoding, logic
import beaker as bk
import _catalogo as ct
import base64
import json
from prettytable import PrettyTable

PAYMENT_AMT = int(1000000) # 1 million microAlgos = 1 Algo

def generate_algorand_keypair():
    # Generate a public/private key pair with the generate_account function
    private_key, account_address = account.generate_account()
    print("Base64 Private Key: {}\nPublic Algorand Address: {}\n".format(private_key,account_address))
    return private_key, account_address

def decode_account(state, data_type):
    if data_type == "apps-local":
        for i in range(len(state["apps-local-state"])):
            for item in state["apps-local-state"][i]["key-value"]:
                decode_field(state,item)
    elif data_type == "created-apps":
        for i in range(len(state['created-apps'])):
            if 'local-state' in state['created-apps'][i]['params']:
                for item in state['created-apps'][i]['params']['local-state']:
                    decode_field(state,item)
            if 'global-state' in state['created-apps'][i]['params']:
                for item in state['created-apps'][i]['params']['global-state']:
                    decode_field(state,item)
    elif data_type == "accounts":
        for i in range(len(state['accounts'])):
            if 'apps-local-state' in state['accounts'][i]:
                for j in range(len(state['accounts'][i]['apps-local-state'])):
                    if 'key-value' in state['accounts'][i]['apps-local-state'][j]:
                        for item in state['accounts'][i]['apps-local-state'][j]['key-value']:
                            decode_field(state,item)
    else:
        raise ValueError(f"Invalid data type: {data_type}")
    return state

def decode_field(state,item):
    key = item["key"]
    value = item["value"]
    try:
        state_key = base64.b64decode(key).decode("utf-8")
    except:
        state_key = str(base64.b64decode(key))
    item["key"] = state_key

    if value["type"] == 1:
        # byte string
        state_value = base64.b64decode(value["bytes"])

        if(len(state_value)==32):
            state_value = encoding.encode_address(state_value)
        else:
            state_value = state_value.decode()
        state[state_key] = state_value
        item["value"]["bytes"] = state_value
    else:
        # integer
        state[state_key] = value["uint"]
        item["value"]["uint"] = state[state_key]

def catalog_of_provider(state):
    """CORRECT VERSION of the function to display the catalog"""
    decode_account(state,"accounts")

    table = PrettyTable()
    table.title = "Provider Catalog"
    table.field_names = ["Address", "NetID", "Provider Name", "Endpoint of Smart Contract"]

    for account in state['accounts']:
        address = account['address']
        if 'apps-local-state' in account:
            for i in range(len(account['apps-local-state'])):
                if 'key-value' in account['apps-local-state'][i]:
                    # Initialize variables
                    netid = ""
                    provider_name = ""
                    endpoint = 0

                    # Search for all necessary fields
                    for j in range(len(account['apps-local-state'][i]['key-value'])):
                        key = account['apps-local-state'][i]['key-value'][j]['key']
                        if key == 'NetID':
                            netid = account['apps-local-state'][i]['key-value'][j]['value']['bytes']
                        elif key == 'Provider Name':
                            provider_name = account['apps-local-state'][i]['key-value'][j]['value']['bytes']
                        elif key == 'Endpoint of Smart Contract':
                            # CORRECTION: Use [i] instead of [0]
                            endpoint = account['apps-local-state'][i]['key-value'][j]['value']['uint']

                    # Add to table only if all fields are present
                    if netid and provider_name and endpoint:
                        entry = [address, netid, provider_name, endpoint]
                        table.add_row(entry, divider=True)

    return table

def find_addr_from_netid(netid, state):
    """CORRECT VERSION of the function to find address from NetID"""
    decode_account(state, "accounts")

    for account in state['accounts']:
        address = account['address']
        if 'apps-local-state' in account:
            for j in range(len(account['apps-local-state'])):
                if 'key-value' in account['apps-local-state'][j]:
                    # Initialize variables
                    found_netid = ""
                    name_provider = ""
                    endpoint = 0

                    # Search for all fields
                    for i in range(len(account['apps-local-state'][j]['key-value'])):
                        key = account['apps-local-state'][j]['key-value'][i]['key']
                        if key == 'NetID':
                            found_netid = account['apps-local-state'][j]['key-value'][i]['value']['bytes']
                        elif key == 'Provider Name':
                            name_provider = account['apps-local-state'][j]['key-value'][i]['value']['bytes']
                        elif key == 'Endpoint of Smart Contract':
                            endpoint = account['apps-local-state'][j]['key-value'][i]['value']['uint']

                    # Check if we found the searched NetID
                    if found_netid == netid and name_provider and endpoint:
                        return address, name_provider, endpoint

    return "Not Found!", "Not Found!", "Not Found!"

def waitForInput():
    input('Press enter to continue...')

def menu(account_info_LoRa, algod_client, acct_LoRa):
    print("\nAvailable operations")
    while True:
        print("\nSelect an option:")
        print("1. Deploy the catalog app")
        print("2. Delete the catalog app from on-chain apps")
        print("3. Application info")
        print("4. Account info")
        print("5. Complete catalog")
        print("6. Find the address of a netID")
        print("7. Get provider info from catalog (using smart contract)")
        print("8. Check if provider exists")
        print("0. Exit menu")

        choice = input()

        if choice == "1":
            print("You chose Option 1 - Deploy the catalog app")

            if (len(account_info_LoRa['created-apps'])==0):
                # create catalog app client
                app_client_catalog = bk.client.ApplicationClient(
                    client=algod_client,
                    app=ct.app,
                    sender=acct_LoRa.address,
                    signer=acct_LoRa.signer,
                )

                app_id_catalog, address_catalog, txid_catalog = app_client_catalog.create()
                print(
                    f"""Deployed catalog app in txid {txid_catalog}
                    App ID: {app_id_catalog}
                    Address: {address_catalog}
                """
                )

                waitForInput()

                # Check and decode information about LoRa account
                print("LoRa account info:")
                account_info_LoRa = algod_client.account_info(acct_LoRa.address)
                try:
                    print(json.dumps(decode_account(account_info_LoRa, "created-apps"),indent=4))
                except:
                    print(json.dumps(account_info_LoRa,indent=4))

                waitForInput()

                # Get catalog app info
                app_catalog_info = app_client_catalog.get_application_account_info()
                print("Catalog application info")
                print(json.dumps(app_catalog_info,indent=4))
            else:
                print("The app has already been deployed!\n")

            waitForInput()

        elif choice == "2":
            print("You chose Option 2 - Delete the catalog app")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                # connect client to existing catalog app
                app_client_catalog = bk.client.ApplicationClient(
                    client=algod_client,
                    app=ct.app,
                    app_id=app_id_catalog,
                    sender=acct_LoRa.address,
                    signer=acct_LoRa.signer,
                )

                address_catalog = logic.get_application_address(app_id_catalog)
                app_client_catalog.delete()
                print(f"App deleted from LoRa account address: {acct_LoRa.address}")

                waitForInput()

                print("LoRa account info:")
                account_info_LoRa = algod_client.account_info(acct_LoRa.address)
                try:
                    print(json.dumps(decode_account(account_info_LoRa, "created-apps"),indent=4))
                except:
                    print(json.dumps(account_info_LoRa,indent=4))
            else:
                print("App not found!\n")

            waitForInput()

        elif choice == "3":
            print("You chose Option 3 - Application info")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                # connect client to existing catalog app
                app_client_catalog = bk.client.ApplicationClient(
                    client=algod_client,
                    app=ct.app,
                    app_id=app_id_catalog,
                    sender=acct_LoRa.address,
                    signer=acct_LoRa.signer,
                )

                # Get catalog app info
                app_catalog_info = app_client_catalog.get_application_account_info()
                print("Catalog application info")
                print(json.dumps(app_catalog_info,indent=4))
            else:
                print("App not found!\n")

            waitForInput()

        elif choice == "4":
            print("You chose Option 4 - Account info")

            print("LoRa account info:")
            try:
                print(json.dumps(decode_account(account_info_LoRa, "created-apps"),indent=4))
            except:
                print(json.dumps(account_info_LoRa,indent=4))

            waitForInput()

        elif choice == "5":
            print("You chose Option 5 - Complete catalog")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                try:
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_catalog)
                    table = catalog_of_provider(response)
                    print(table)
                except Exception as e:
                    print(f"Error retrieving catalog: {e}")
            else:
                print("App not found!\n")

            waitForInput()

        elif choice == "6":
            print("You chose Option 6 - Find address from NetID")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                try:
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_catalog)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)

                    print(f"\nSearch Results for NetID: {netid}")
                    print(f"Address: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")
                except Exception as e:
                    print(f"Error searching for NetID: {e}")
            else:
                print("App not found!\n")

            waitForInput()

        elif choice == "7":
            print("You chose Option 7 - Get provider info using smart contract")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                # connect client to existing catalog app
                app_client_catalog = bk.client.ApplicationClient(
                    client=algod_client,
                    app=ct.app,
                    app_id=app_id_catalog,
                    sender=acct_LoRa.address,
                    signer=acct_LoRa.signer,
                )

                provider_address = input("Enter the provider address: ")
                try:
                    # Use the get_entry_provider function from catalog
                    result = app_client_catalog.call(
                        ct.get_entry_provider,
                        provider=provider_address
                    )
                    print("Provider Info:", result.return_value)
                except Exception as e:
                    print(f"Error getting provider info: {e}")
            else:
                print("App not found!\n")

            waitForInput()

        elif choice == "8":
            print("You chose Option 8 - Check if provider exists")

            if (len(account_info_LoRa['created-apps'])==1):
                app_id_catalog = account_info_LoRa['created-apps'][0]["id"]
                # connect client to existing catalog app
                app_client_catalog = bk.client.ApplicationClient(
                    client=algod_client,
                    app=ct.app,
                    app_id=app_id_catalog,
                    sender=acct_LoRa.address,
                    signer=acct_LoRa.signer,
                )

                provider_address = input("Enter the provider address: ")
                try:
                    # Use the new provider_exists function
                    result = app_client_catalog.call(
                        ct.provider_exists,
                        provider=provider_address
                    )
                    exists = "YES" if result.return_value else "NO"
                    print(f"Provider {provider_address} exists: {exists}")
                except Exception as e:
                    print(f"Error checking provider existence: {e}")
            else:
                print("App not found!\n")

            waitForInput()

        elif choice.lower() == "0":
            print("Exiting menu.")
            break
        else:
            print("Invalid option. Please try again.")

## Create connection to network via public algod API
algod_client = bk.localnet.get_algod_client()

# Get LoRa account from localnet
accounts = bk.localnet.kmd.get_accounts()
LoRa_account = accounts[0]
LoRa_account_address = LoRa_account.address
LoRa_private_key = LoRa_account.private_key

acct_LoRa = bk.localnet.LocalAccount(address=LoRa_account_address, private_key=LoRa_private_key)

# WARNING: this is just an example, you should never write sensitive information
print(
    f"""Account
    Address: {acct_LoRa.address}
    Private key: {acct_LoRa.private_key}
"""
)

waitForInput()

# Check LoRa account balance
account_info_LoRa = algod_client.account_info(acct_LoRa.address)
print("LoRa account info:")
print("Account balance: {} microAlgos".format(account_info_LoRa.get('amount')) + "\n")

waitForInput()

# Check balance of account via algod
while account_info_LoRa.get('amount')==0:
    print("Dispense ALGO at https://testnet.algoexplorer.io/dispenser or here https://dispenser.testnet.aws.algodev.network. Script will continue once ALGO is received...")
    waitForInput()
    account_info_LoRa = algod_client.account_info(acct_LoRa.address)

print("{} funded!".format(acct_LoRa.address))

waitForInput()

# Check and decode information about LoRa account
print("LoRa account info:")
account_info_LoRa = algod_client.account_info(acct_LoRa.address)
try:
    print(json.dumps(decode_account(account_info_LoRa, "created-apps"),indent=4))
except:
    print(json.dumps(account_info_LoRa,indent=4))

waitForInput()

menu(account_info_LoRa, algod_client, acct_LoRa)
