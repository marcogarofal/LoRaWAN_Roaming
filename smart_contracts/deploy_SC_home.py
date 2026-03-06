#deploy_SC_home.py

from beaker.client.api_providers import AlgoNode, Network
from algosdk import account, encoding, logic
import beaker as bk
import _SC as sla
import _catalogo as ct
from algosdk import atomic_transaction_composer, transaction
import base64
import json
from prettytable import PrettyTable

PAYMENT_AMT = int(1000000) # 1 million microAlgos = 1 Algo
NETID = "00000002" #My NetID
NAME_PROVIDER="Tim" #My Provider Name

def generate_algorand_keypair():
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
        state_value = base64.b64decode(value["bytes"])
        if(len(state_value)==32):
            state_value = encoding.encode_address(state_value)
        else:
            state_value = state_value.decode()
        state[state_key] = state_value
        item["value"]["bytes"] = state_value
    else:
        state[state_key] = value["uint"]
        item["value"]["uint"] = state[state_key]

def catalog_of_provider(state):
    decode_account(state,"accounts")
    table = PrettyTable()
    table.title = "Provider Catalog"
    table.field_names = ["Address", "NetID", "Provider Name", "Endpoint of Smart Contract"]

    for account in state['accounts']:
        address = account['address']
        if 'apps-local-state' in account:
            for i in range(len(account['apps-local-state'])):
                if 'key-value' in account['apps-local-state'][i]:
                    netid = ""
                    provider_name = ""
                    endpoint = 0

                    for j in range(len(account['apps-local-state'][i]['key-value'])):
                        key = account['apps-local-state'][i]['key-value'][j]['key']
                        if key == 'NetID':
                            netid = account['apps-local-state'][i]['key-value'][j]['value']['bytes']
                        elif key == 'Provider Name':
                            provider_name = account['apps-local-state'][i]['key-value'][j]['value']['bytes']
                        elif key == 'Endpoint of Smart Contract':
                            endpoint = account['apps-local-state'][i]['key-value'][j]['value']['uint']

                    if netid and provider_name and endpoint:
                        entry = [address, netid, provider_name, endpoint]
                        table.add_row(entry, divider=True)
    return table

def find_addr_from_netid(netid, state):
    decode_account(state, "accounts")
    for account in state['accounts']:
        address = account['address']
        if 'apps-local-state' in account:
            for j in range(len(account['apps-local-state'])):
                if 'key-value' in account['apps-local-state'][j]:
                    found_netid = ""
                    name_provider = ""
                    endpoint = 0

                    for i in range(len(account['apps-local-state'][j]['key-value'])):
                        key = account['apps-local-state'][j]['key-value'][i]['key']
                        if key == 'NetID':
                            found_netid = account['apps-local-state'][j]['key-value'][i]['value']['bytes']
                        elif key == 'Provider Name':
                            name_provider = account['apps-local-state'][j]['key-value'][i]['value']['bytes']
                        elif key == 'Endpoint of Smart Contract':
                            endpoint = account['apps-local-state'][j]['key-value'][i]['value']['uint']

                    if found_netid == netid and name_provider and endpoint:
                        return address, name_provider, endpoint
    return "Not Found!", "Not Found!", "Not Found!"

def waitForInput():
    input('Press enter to continue...')

def menu(account_info_Provider, algod_client, acct_Provider):
    print("\nAvailable operations")
    while True:
        print("\nSelect an option:")
        print("1. Deploy the Smart Contract")
        print("2. Delete the Smart Contract from on-chain apps")
        print("3. Application info")
        print("4. Account info")
        print("5. Complete catalog")
        print("6. Smart Contract initialization")
        print("7. Opt-in to catalog")
        print("8. Close-out from catalog")
        print("9. Register in the catalog")
        print("10. Find address from netID")
        print("11. Confirm packet sending or SLA creation (forwarder side)")
        print("12. View an SLA (home side)")
        print("13. View an SLA (forwarder side)")
        print("14. Received a packet, increment counter (home side)")
        print("15. Ban a provider (home side)")
        print("16. Get SLA statistics")
        print("17. Check opt-in status")
        print("0. Exit menu")

        choice = input()

        if choice == "1":
            print("You chose Option 1 - Deploy the Smart Contract")

            if (len(account_info_Provider['created-apps'])==0):
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_SC, address_SC, txid_SC = app_client_SC.create()
                print(f"""Deployed Smart Contract in txid {txid_SC}
                    App ID: {app_id_SC}
                    Address: {address_SC}""")
                app_client_SC.fund(10 * bk.consts.algo)

                waitForInput()

                print("Provider account info:")
                account_info_Provider = algod_client.account_info(acct_Provider.address)
                try:
                    print(json.dumps(decode_account(account_info_Provider, "created-apps"),indent=4))
                except:
                    print(json.dumps(account_info_Provider,indent=4))

                waitForInput()

                app_SC_info = app_client_SC.get_application_account_info()
                print("Smart Contract application info")
                print(json.dumps(app_SC_info,indent=4))
            else:
                print("The app has already been deployed!")

            waitForInput()

        elif choice == "2":
            print("You chose Option 2 - Delete the Smart Contract")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    app_client_catalog = bk.client.ApplicationClient(
                        client=algod_client,
                        app=ct.app,
                        app_id=app_id_cat.return_value,
                        sender=acct_Provider.address,
                        signer=acct_Provider.signer,
                    )
                    try:
                        app_client_catalog.clear_state()
                    except:
                        print("Already cleared state or not opted in")

                app_client_SC.delete()
                print(f"App deleted from Provider account")

                waitForInput()

                print("Provider account info:")
                account_info_Provider = algod_client.account_info(acct_Provider.address)
                try:
                    print(json.dumps(decode_account(account_info_Provider, "created-apps"),indent=4))
                except:
                    print(json.dumps(account_info_Provider,indent=4))
            else:
                print("App not found!")

            waitForInput()

        elif choice == "3":
            print("You chose Option 3 - Application info")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                b = int(input("Enter the amount of ALGO to fund: "))
                app_client_SC.fund(b * bk.consts.algo)

                app_SC_info = app_client_SC.get_application_account_info()
                print("Smart Contract application info")
                print(json.dumps(app_SC_info,indent=4))
            else:
                print("App not found!")

            waitForInput()

        elif choice == "4":
            print("You chose Option 4 - Account info")

            print("Provider account info:")
            try:
                print(json.dumps(decode_account(account_info_Provider, "created-apps"),indent=4))
            except:
                print(json.dumps(account_info_Provider,indent=4))

            waitForInput()

        elif choice == "5":
            print("You chose Option 5 - Complete catalog")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    table = catalog_of_provider(response)
                    print(table)
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "6":
            print("You chose Option 6 - Smart Contract initialization")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_cat = int(input("Enter the catalog endpoint: "))
                price = int(input("Enter the price for each SLA (mALGO): "))
                threshold = int(input("Enter the minimum number of packets for each SLA: "))
                tolerance = int(input("Enter the minimum percentage of packets that cannot be lost for each SLA (%): "))
                payment_tolerance = int(input("Enter the payment tolerance percentage (e.g., 95 for 95%): "))
                token = input("Enter the token: ")
                gwid = input("Enter the gateway id: ")

                result = app_client_SC.call(
                    sla.init,
                    app_id_catalog=app_cat,
                    price=price,
                    threshold=threshold,
                    tolerance=tolerance,
                    payment_tolerance=payment_tolerance,
                    token=token,
                    gwid=gwid,
                )
                print(result.return_value)
            else:
                print("App not found!")
            waitForInput()

        elif choice == "7":
            print("You chose Option 7 - Opt-in to catalog")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    app_client_catalog = bk.client.ApplicationClient(
                        client=algod_client,
                        app=ct.app,
                        app_id=app_id_cat.return_value,
                        sender=acct_Provider.address,
                        signer=acct_Provider.signer,
                    )

                    LoRa = algod_client.application_info(app_id_cat.return_value)
                    sp = algod_client.suggested_params()
                    ptxn = atomic_transaction_composer.TransactionWithSigner(
                        txn=transaction.PaymentTxn(
                            sender=acct_Provider.address,
                            sp=sp,
                            receiver=LoRa["params"]["creator"],
                            amt=(PAYMENT_AMT * int(1))
                        ),
                        signer=acct_Provider.signer
                    )

                    try:
                        app_client_catalog.opt_in(payment=ptxn)
                        print(f"✅ App opted-in from Provider account address: {acct_Provider.address}")
                    except Exception as e:
                        print(f"❌ Opt-in failed: {e}")
                        if "already opted in" in str(e).lower():
                            print("App already opted-in")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "8":
            print("You chose Option 8 - Close-out from catalog")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    app_client_catalog = bk.client.ApplicationClient(
                        client=algod_client,
                        app=ct.app,
                        app_id=app_id_cat.return_value,
                        sender=acct_Provider.address,
                        signer=acct_Provider.signer,
                    )

                    try:
                        app_client_catalog.close_out()
                        print(f"App closed-out from Provider account address: {acct_Provider.address}")
                    except:
                        print("App already closed-out")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "9":
            print("You chose Option 9 - Register in the catalog")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    app_client_catalog = bk.client.ApplicationClient(
                        client=algod_client,
                        app=ct.app,
                        app_id=app_id_cat.return_value,
                        sender=acct_Provider.address,
                        signer=acct_Provider.signer,
                    )

                    result = app_client_catalog.call(
                        ct.set_entry_provider,
                        NetID_Provider=NETID,
                        Name_Provider=NAME_PROVIDER,
                        app_id_SC_Provider=app_id_SC,
                    )
                    print(result.return_value)
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "10":
            print("You chose Option 10 - Find address from netID")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "11":
            print("You chose Option 11 - Confirm packet sending or SLA creation (forwarder side)")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")

                    if(addr_account != "Not Found!"):
                        value = app_client_SC.call(
                            sla.sla_check,
                            NetID_home=netid,
                            provider=acct_Provider.address,
                            cat_ref=app_id_cat.return_value,
                            Name_home_Provider=name_provider,
                            Endpoint_home_SC=endpoint_sc,
                            boxes=[(app_client_SC.app_id, netid+"_forward_box"), (endpoint_sc, NETID+"_home_box")]
                        )
                        print("SLA Check Result:", value.return_value)

                        try:
                            value = app_client_SC.call(
                                sla.getSLA,
                                type_op="_forward_box",
                                NetID=netid,
                                boxes=[(app_client_SC.app_id, netid+"_forward_box")],
                            )
                            print("Forward SLA:", value.return_value)
                        except:
                            print(f"SLA {netid}_forward_box does not exist")
                    else:
                        print(f"NetID {netid} not found!")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "12":
            print("You chose Option 12 - View an SLA (home side)")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")

                    if(addr_account != "Not Found!"):
                        try:
                            value = app_client_SC.call(
                                sla.getSLA,
                                type_op="_home_box",
                                NetID=netid,
                                boxes=[(app_client_SC.app_id, netid+"_home_box")],
                            )
                            print("Home SLA:", value.return_value)
                        except:
                            print(f"SLA {netid}_home_box does not exist")
                    else:
                        print(f"NetID {netid} not found!")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "13":
            print("You chose Option 13 - View an SLA (forwarder side)")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")

                    if(addr_account != "Not Found!"):
                        try:
                            value = app_client_SC.call(
                                sla.getSLA,
                                type_op="_forward_box",
                                NetID=netid,
                                boxes=[(app_client_SC.app_id, netid+"_forward_box")],
                            )
                            print("Forward SLA:", value.return_value)
                        except:
                            print(f"SLA {netid}_forward_box does not exist")
                    else:
                        print(f"NetID {netid} not found!")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "14":
            print("You chose Option 14 - Received a packet, increment counter (home side)")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")

                    if(addr_account != "Not Found!"):
                        value = app_client_SC.call(
                            sla.receive_packet_from_forwarder,
                            NetID_forwarder=netid,
                            boxes=[(app_client_SC.app_id, netid+"_home_box")]
                        )
                        print("Packet received:", value.return_value)

                        value = app_client_SC.call(
                            sla.getSLA,
                            type_op="_home_box",
                            NetID=netid,
                            boxes=[(app_client_SC.app_id, netid+"_home_box")],
                        )
                        print("Updated SLA:", value.return_value)
                    else:
                        print(f"NetID {netid} not found!")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "15":
            print("You chose Option 15 - Ban a provider (home side)")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    addr_account, name_provider, endpoint_sc = find_addr_from_netid(netid, response)
                    print(f"\nAddress: {addr_account}")
                    print(f"Provider name: {name_provider}")
                    print(f"Smart Contract Endpoint: {endpoint_sc}")

                    if(addr_account != "Not Found!"):
                        result = app_client_SC.call(
                            sla.ban_home_function,
                            NetID_forwarder=netid,
                            boxes=[(app_client_SC.app_id, netid+"_home_box")]
                        )
                        print("Ban result:", result.return_value)
                    else:
                        print(f"NetID {netid} not found!")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "16":
            print("You chose Option 16 - Get SLA statistics")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    indexer_client = bk.localnet.get_indexer_client()
                    response = indexer_client.accounts(application_id=app_id_cat.return_value)
                    netid = input("Enter the NetID of a provider: ")
                    type_op = input("Enter SLA type (_home_box or _forward_box): ")

                    try:
                        result = app_client_SC.call(
                            sla.get_sla_stats,
                            NetID=netid,
                            type_op=type_op,
                            boxes=[(app_client_SC.app_id, netid + type_op)]
                        )
                        print("SLA Statistics:")
                        print(result.return_value)
                    except Exception as e:
                        print(f"Error getting SLA stats: {e}")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice == "17":
            print("You chose Option 17 - Check opt-in status")

            if (len(account_info_Provider['created-apps'])==1):
                app_id_SC = account_info_Provider['created-apps'][0]["id"]
                app_client_SC = bk.client.ApplicationClient(
                    client=algod_client,
                    app=sla.app,
                    app_id=app_id_SC,
                    sender=acct_Provider.address,
                    signer=acct_Provider.signer,
                )

                app_id_cat = app_client_SC.call(sla.get_appID_cat)
                if(app_id_cat.return_value != 0):
                    try:
                        account_info = algod_client.account_info(acct_Provider.address)
                        opted_apps = [app['id'] for app in account_info.get('apps-local-state', [])]

                        if app_id_cat.return_value in opted_apps:
                            print(f"✅ Account IS opted-in to catalog {app_id_cat.return_value}")
                        else:
                            print(f"❌ Account is NOT opted-in to catalog {app_id_cat.return_value}")
                            print("Please run Option 7 (Opt-in to catalog) first")

                    except Exception as e:
                        print(f"Error checking opt-in status: {e}")
                else:
                    print("Smart Contract not initialized")
            else:
                print("App not found!")

            waitForInput()

        elif choice.lower() == "0":
            print("Exiting menu.")
            break
        else:
            print("Invalid option. Please try again.")

# Setup network connection and accounts
algod_client = bk.localnet.get_algod_client()

accounts = bk.localnet.kmd.get_accounts()
Provider_account = accounts[1]  # Provider 2 uses accounts[1]
Provider_account_address = Provider_account.address
Provider_account_key = Provider_account.private_key

acct_Provider = bk.localnet.LocalAccount(address=Provider_account_address, private_key=Provider_account_key)

print(f"""Account
    Address: {acct_Provider.address}
    Private key: {acct_Provider.private_key}""")

waitForInput()

# Check Provider account balance
account_info_Provider = algod_client.account_info(acct_Provider.address)
print("Provider account info:")
print("Account balance: {} microAlgos".format(account_info_Provider.get('amount')) + "\n")

waitForInput()

# Check balance of account via algod
while account_info_Provider.get('amount')==0:
    print("Dispense ALGO at https://testnet.algoexplorer.io/dispenser or here https://dispenser.testnet.aws.algodev.network. Script will continue once ALGO is received...")
    waitForInput()
    account_info_Provider = algod_client.account_info(acct_Provider.address)

print("{} funded!".format(acct_Provider.address))

waitForInput()

# Check and decode information about Provider account
print("Provider account info:")
account_info_Provider = algod_client.account_info(acct_Provider.address)
try:
    print(json.dumps(decode_account(account_info_Provider, "created-apps"),indent=4))
except:
    print(json.dumps(account_info_Provider,indent=4))

waitForInput()

menu(account_info_Provider, algod_client, acct_Provider)
