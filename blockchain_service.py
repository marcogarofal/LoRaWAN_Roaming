from flask import Flask, request, jsonify
import os
import sys
import json
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
import threading

# Import moduli Smart Contract
PYTHON_SCRIPTS_PATH = os.path.expanduser('/home/ubuntu/block-forwarder-mqtt/smart_contract/')
sys.path.insert(0, PYTHON_SCRIPTS_PATH)

try:
    import _SC as sla
    import _catalogo as ct
    import beaker as bk
    from algosdk import account
    print(f"✅ Imported Smart Contract modules from: {PYTHON_SCRIPTS_PATH}")
except ImportError as e:
    print(f"❌ Failed to import Smart Contract modules: {e}")
    print(f"   Make sure {PYTHON_SCRIPTS_PATH} contains _SC.py and _catalogo.py")
    sys.exit(1)

app = Flask(__name__)

# Thread pool per operazioni async
executor = ThreadPoolExecutor(max_workers=10)

# Global state
CONFIG = {
    'initialized': False,
    'my_netid': None,
    'my_provider_name': None,
    'my_role': None,
    'algod_client': None,
    'indexer_client': None,
    'account': None,
    'sc_app_id': None,
    'catalog_app_id': None,
}

# ============================================================================
# 🚀 CACHING SYSTEM
# ============================================================================

class CacheManager:
    """Gestore cache thread-safe con TTL"""
    
    def __init__(self):
        self.catalog_cache = {}  # {netid: (data, timestamp)}
        self.sla_cache = {}      # {netid: (data, timestamp)}
        self.config_cache = {}   # {key: (data, timestamp)}
        self.lock = threading.Lock()
        
        # TTL settings (secondi)
        self.CATALOG_TTL = 300   # 5 minuti - catalog cambia raramente
        self.SLA_TTL = 60        # 1 minuto - SLA puo' cambiare
        self.CONFIG_TTL = 600    # 10 minuti - config molto stabile
    
    def get_catalog(self, netid):
        """Recupera provider dal cache"""
        with self.lock:
            if netid in self.catalog_cache:
                data, timestamp = self.catalog_cache[netid]
                if time.time() - timestamp < self.CATALOG_TTL:
                    print(f"✅ Cache HIT - Catalog: {netid}")
                    return data
                else:
                    print(f"⏰ Cache EXPIRED - Catalog: {netid}")
            else:
                print(f"❌ Cache MISS - Catalog: {netid}")
        return None
    
    def set_catalog(self, netid, data):
        """Salva provider nel cache"""
        with self.lock:
            self.catalog_cache[netid] = (data, time.time())
            print(f"💾 Cache SET - Catalog: {netid}")
    
    def get_sla(self, netid):
        """Recupera SLA dal cache"""
        with self.lock:
            if netid in self.sla_cache:
                data, timestamp = self.sla_cache[netid]
                if time.time() - timestamp < self.SLA_TTL:
                    return data
        return None
    
    def set_sla(self, netid, data):
        """Salva SLA nel cache"""
        with self.lock:
            self.sla_cache[netid] = (data, time.time())
    
    def get_config(self, key):
        """Recupera config dal cache"""
        with self.lock:
            if key in self.config_cache:
                data, timestamp = self.config_cache[key]
                if time.time() - timestamp < self.CONFIG_TTL:
                    return data
        return None
    
    def set_config(self, key, data):
        """Salva config nel cache"""
        with self.lock:
            self.config_cache[key] = (data, time.time())
    
    def invalidate_catalog(self, netid=None):
        """Invalida cache del catalogo"""
        with self.lock:
            if netid:
                self.catalog_cache.pop(netid, None)
            else:
                self.catalog_cache.clear()
            print(f"🗑️  Cache INVALIDATED - Catalog: {netid or 'ALL'}")
    
    def clear_all(self):
        """Cancella tutto il cache"""
        with self.lock:
            self.catalog_cache.clear()
            self.sla_cache.clear()
            self.config_cache.clear()
            print("🗑️  Cache CLEARED - All")

# Istanza globale del cache manager
cache_mgr = CacheManager()

# ============================================================================
# 🔍 CATALOG INDEX - Indice locale per ricerca veloce
# ============================================================================

class CatalogIndex:
    """Indice locale del catalogo per ricerca O(1)"""
    
    def __init__(self):
        self.index = {}  # {netid: (address, name, endpoint)}
        self.last_update = 0
        self.update_interval = 300  # Aggiorna ogni 5 minuti
        self.lock = threading.Lock()
    
    def needs_update(self):
        """Verifica se l'indice deve essere aggiornato"""
        return time.time() - self.last_update > self.update_interval
    
    def build_index(self, indexer_client, catalog_app_id):
        """Costruisce l'indice scaricando tutto il catalogo"""
        print(f"\n{'='*60}")
        print(f"🔨 Building catalog index...")
        print(f"{'='*60}")
        
        start_time = time.time()
        new_index = {}
        
        try:
            # Query indexer per tutti gli account
            response = indexer_client.accounts(
                application_id=catalog_app_id
            )
            
            # Parse tutti i provider
            for account_data in response['accounts']:
                address = account_data['address']
                
                if 'apps-local-state' in account_data:
                    for app_state in account_data['apps-local-state']:
                        if app_state.get('id') == catalog_app_id:
                            kv = app_state.get('key-value', [])
                            
                            # Extract NetID, Name, Endpoint
                            found_netid = None
                            name_provider = None
                            endpoint_sc = None
                            
                            for item in kv:
                                import base64
                                key = base64.b64decode(item['key']).decode('utf-8')
                                
                                if key == 'NetID':
                                    found_netid = base64.b64decode(item['value']['bytes']).decode('utf-8')
                                elif key == 'Provider Name':
                                    name_provider = base64.b64decode(item['value']['bytes']).decode('utf-8')
                                elif key == 'Endpoint of Smart Contract':
                                    endpoint_sc = item['value']['uint']
                            
                            if found_netid:
                                new_index[found_netid] = (address, name_provider, endpoint_sc)
            
            with self.lock:
                self.index = new_index
                self.last_update = time.time()
            
            elapsed = time.time() - start_time
            print(f"✅ Catalog index built: {len(new_index)} providers in {elapsed:.2f}s")
            return True
            
        except Exception as e:
            print(f"❌ Failed to build catalog index: {e}")
            return False
    
    def get_provider(self, netid):
        """Ricerca veloce O(1) nel catalogo"""
        with self.lock:
            return self.index.get(netid)
    
    def get_all_providers(self):
        """Ritorna tutti i provider nell'indice"""
        with self.lock:
            return dict(self.index)

# Istanza globale dell'indice
catalog_index = CatalogIndex()

# ============================================================================
# 🔄 ASYNC HELPERS
# ============================================================================

def async_route(f):
    """Decorator per rendere le route Flask asincrone"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            loop.close()
    return wrapped

async def run_in_executor(func, *args):
    """Esegue funzione sincrona in thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)

# ============================================================================
# 📡 BLOCKCHAIN OPERATIONS (con cache)
# ============================================================================

def find_provider_by_netid_sync(netid):
    """Versione sincrona ottimizzata con cache e index"""
    
    # 1. Prova cache
    cached = cache_mgr.get_catalog(netid)
    if cached:
        return cached
    
    # 2. Prova index locale
    if not catalog_index.needs_update():
        provider = catalog_index.get_provider(netid)
        if provider:
            print(f"✅ Index HIT - NetID: {netid}")
            cache_mgr.set_catalog(netid, provider)
            return provider
    
    # 3. Aggiorna index se necessario
    if catalog_index.needs_update():
        print(f"🔄 Index needs update, rebuilding...")
        catalog_index.build_index(
            CONFIG['indexer_client'],
            CONFIG['catalog_app_id']
        )
        
        provider = catalog_index.get_provider(netid)
        if provider:
            cache_mgr.set_catalog(netid, provider)
            return provider
    
    # 4. Fallback: ricerca diretta (lenta)
    print(f"⚠️  Fallback to direct search for NetID: {netid}")
    return find_provider_direct_search(netid)

def find_provider_direct_search(netid):
    """Ricerca diretta nel catalogo (fallback lento)"""
    if not CONFIG['initialized']:
        raise Exception("Service not initialized")
    
    print(f"\n{'='*60}")
    print(f"🔍 Direct search for NetID: {netid}")
    print(f"{'='*60}")
    
    response = CONFIG['indexer_client'].accounts(
        application_id=CONFIG['catalog_app_id']
    )
    
    for account_data in response['accounts']:
        address = account_data['address']
        
        if 'apps-local-state' in account_data:
            for app_state in account_data['apps-local-state']:
                if app_state.get('id') == CONFIG['catalog_app_id']:
                    kv = app_state.get('key-value', [])
                    
                    found_netid = None
                    name_provider = None
                    endpoint_sc = None
                    
                    for item in kv:
                        import base64
                        key = base64.b64decode(item['key']).decode('utf-8')
                        
                        if key == 'NetID':
                            found_netid = base64.b64decode(item['value']['bytes']).decode('utf-8')
                        elif key == 'Provider Name':
                            name_provider = base64.b64decode(item['value']['bytes']).decode('utf-8')
                        elif key == 'Endpoint of Smart Contract':
                            endpoint_sc = item['value']['uint']
                    
                    if found_netid == netid:
                        result = (address, name_provider, endpoint_sc)
                        cache_mgr.set_catalog(netid, result)
                        return result
    
    raise Exception(f"Provider with NetID {netid} not found")

async def find_provider_by_netid_async(netid):
    """Versione asincrona della ricerca provider"""
    return await run_in_executor(find_provider_by_netid_sync, netid)

def check_sla_sync(netid_full, provider_address, provider_name, endpoint_sc):
    """Versione sincrona di SLA check"""
    
    # Check cache
    cached_sla = cache_mgr.get_sla(netid_full)
    if cached_sla:
        print(f"✅ SLA Cache HIT: {netid_full}")
        return cached_sla
    
    # Setup Smart Contract client
    app_client_sc = bk.client.ApplicationClient(
        client=CONFIG['algod_client'],
        app=sla.app,
        app_id=CONFIG['sc_app_id'],
        sender=CONFIG['account'].address,
        signer=CONFIG['account'].signer,
    )
    
    # Call sla_check
    print(f"📡 Calling sla_check on Smart Contract...")
    result = app_client_sc.call(
        sla.sla_check,
        NetID_home=netid_full,
        provider=CONFIG['account'].address,
        cat_ref=CONFIG['catalog_app_id'],
        Name_home_Provider=provider_name,
        Endpoint_home_SC=endpoint_sc,
        boxes=[
            (CONFIG['sc_app_id'], netid_full + "_forward_box"),
            (endpoint_sc, CONFIG['my_netid'] + "_home_box")
        ]
    )
    
    sla_output = result.return_value
    sla_data = {
        'state': sla_output[0],
        'token': sla_output[1],
        'gwid': sla_output[2]
    }
    
    # Cache result
    cache_mgr.set_sla(netid_full, sla_data)
    
    return sla_data

async def check_sla_async(netid_full, provider_address, provider_name, endpoint_sc):
    """Versione asincrona di SLA check"""
    return await run_in_executor(
        check_sla_sync,
        netid_full,
        provider_address,
        provider_name,
        endpoint_sc
    )

# ============================================================================
# 🌐 FLASK ROUTES
# ============================================================================

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'LoRaWAN Blockchain Service',
        'version': '3.0-OPTIMIZED',
        'initialized': CONFIG['initialized'],
        'cache_stats': {
            'catalog_entries': len(cache_mgr.catalog_cache),
            'sla_entries': len(cache_mgr.sla_cache),
            'index_providers': len(catalog_index.index),
            'index_age_seconds': int(time.time() - catalog_index.last_update) if catalog_index.last_update else 0
        },
        'endpoints': {
            'POST /init': 'Initialize service with blockchain credentials',
            'GET /health': 'Check service health',
            'POST /check_sla': 'Check SLA for a NetID (ASYNC)',
            'POST /check_sla_batch': 'Check multiple SLAs in parallel (NEW)',
            'POST /increment_counter': 'Increment packet counter',
            'POST /get_sla_stats': 'Get SLA statistics',
            'GET /auto_config': 'Get auto-configuration from blockchain',
            'POST /cache/invalidate': 'Invalidate cache (NEW)',
            'GET /catalog/list': 'List all providers in catalog (NEW)',
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'initialized': CONFIG['initialized'],
        'my_netid': CONFIG.get('my_netid'),
        'my_provider': CONFIG.get('my_provider_name'),
        'role': CONFIG.get('my_role'),
        'catalog_app_id': CONFIG.get('catalog_app_id'),
        'cache_stats': {
            'catalog_entries': len(cache_mgr.catalog_cache),
            'sla_entries': len(cache_mgr.sla_cache),
            'index_providers': len(catalog_index.index),
        }
    })

@app.route('/init', methods=['POST'])
def initialize():
    """Initialize blockchain service with Algorand credentials"""
    data = request.json
    
    try:
        # Setup Algorand clients
        algod_address = data['algod_address']
        algod_token = data['algod_token']
        indexer_address = data['indexer_address']
        
        from algosdk.v2client import algod, indexer
        algod_client = algod.AlgodClient(algod_token, algod_address)
        indexer_client = indexer.IndexerClient("", indexer_address)
        
        # Setup account
        from algosdk import mnemonic
        mnemonic_words = data['private_key_mnemonic']
        private_key = mnemonic.to_private_key(mnemonic_words)
        account_address = account.address_from_private_key(private_key)
        
        acct = bk.localnet.LocalAccount(
            address=account_address,
            private_key=private_key
        )
        
        # Get catalog app ID from Smart Contract
        sc_app_id = data['sc_app_id']
        app_client_sc = bk.client.ApplicationClient(
            client=algod_client,
            app=sla.app,
            app_id=sc_app_id,
            sender=acct.address,
            signer=acct.signer,
        )
        
        catalog_result = app_client_sc.call(sla.get_appID_cat)
        catalog_app_id = catalog_result.return_value
        
        if catalog_app_id == 0:
            return jsonify({
                'status': 'error',
                'message': 'Smart Contract not initialized. Run Option 6 first.'
            }), 400
        
        # Store configuration
        CONFIG.update({
            'initialized': True,
            'my_netid': data['my_netid'],
            'my_provider_name': data['my_provider_name'],
            'my_role': 'forwarder' if data.get('is_forwarder', False) else 'home',
            'algod_client': algod_client,
            'indexer_client': indexer_client,
            'account': acct,
            'sc_app_id': sc_app_id,
            'catalog_app_id': catalog_app_id,
        })
        
        # 🚀 Build catalog index immediatamente
        catalog_index.build_index(indexer_client, catalog_app_id)
        
        print(f"✅ Blockchain service initialized")
        print(f"   NetID: {CONFIG['my_netid']}")
        print(f"   Provider: {CONFIG['my_provider_name']}")
        print(f"   Role: {CONFIG['my_role'].upper()}")
        print(f"   SC App ID: {sc_app_id}")
        print(f"   Catalog App ID: {catalog_app_id}")
        
        return jsonify({
            'status': 'ok',
            'address': account_address,
            'sc_app_id': sc_app_id,
            'catalog_app_id': catalog_app_id,
            'my_netid': CONFIG['my_netid'],
            'my_provider_name': CONFIG['my_provider_name'],
            'role': CONFIG['my_role'].upper(),
            'catalog_providers': len(catalog_index.index)
        })
    
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/check_sla', methods=['POST'])
@async_route
async def check_sla():
    """Check SLA for a given NetID (ASYNC VERSION)"""
    if not CONFIG['initialized']:
        return jsonify({
            'status': 'error',
            'message': 'Service not initialized'
        }), 400
    
    data = request.json
    netid_short = data['netid']
    netid_full = f"{netid_short.zfill(8)}"
    
    print(f"\n{'='*60}")
    print(f"🔍 Checking SLA for NetID: {netid_full}")
    print(f"   My NetID: {CONFIG['my_netid']}")
    print(f"   My Role: {CONFIG['my_role'].upper()}")
    print(f"{'='*60}")
    
    try:
        start_time = time.time()
        
        # Find provider (async)
        print(f"📞 Finding provider with NetID {netid_full} in catalog...")
        provider_data = await find_provider_by_netid_async(netid_full)
        provider_address, provider_name, endpoint_sc = provider_data
        
        find_time = time.time() - start_time
        print(f"✅ Found provider in {find_time:.3f}s:")
        print(f"   Address: {provider_address}")
        print(f"   Name: {provider_name}")
        print(f"   Endpoint: {endpoint_sc}")
        
        # Call sla_check (async)
        sla_start = time.time()
        sla_data = await check_sla_async(
            netid_full,
            provider_address,
            provider_name,
            endpoint_sc
        )
        sla_time = time.time() - sla_start
        
        total_time = time.time() - start_time
        
        print(f"✅ SLA Check Result:")
        print(f"   State: {sla_data['state']}")
        print(f"   Token: {sla_data['token']}")
        print(f"   Gateway ID: {sla_data['gwid']}")
        print(f"   Find time: {find_time:.3f}s")
        print(f"   SLA time: {sla_time:.3f}s")
        print(f"   Total time: {total_time:.3f}s")
        
        return jsonify({
            'status': 'ok',
            'sla_state': sla_data['state'],
            'token_broker': sla_data['token'],
            'gateway_id': sla_data['gwid'],
            'message': f"SLA check completed for {provider_name}",
            'performance': {
                'find_time_ms': int(find_time * 1000),
                'sla_time_ms': int(sla_time * 1000),
                'total_time_ms': int(total_time * 1000)
            }
        })
    
    except Exception as e:
        print(f"❌ SLA check failed: {e}")
        return jsonify({
            'status': 'error',
            'sla_state': 'Reject',
            'token_broker': 'None',
            'gateway_id': 'None',
            'message': str(e)
        }), 400

@app.route('/check_sla_batch', methods=['POST'])
@async_route
async def check_sla_batch():
    """
    🚀 NEW: Check multiple SLAs in parallel
    
    Request body:
    {
        "netids": ["02", "03", "04"]
    }
    """
    if not CONFIG['initialized']:
        return jsonify({
            'status': 'error',
            'message': 'Service not initialized'
        }), 400
    
    data = request.json
    netids = data.get('netids', [])
    
    if not netids:
        return jsonify({
            'status': 'error',
            'message': 'No netids provided'
        }), 400
    
    print(f"\n{'='*60}")
    print(f"🚀 BATCH SLA Check for {len(netids)} NetIDs")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    # Crea tasks per tutti i NetID in parallelo
    async def check_one_sla(netid_short):
        try:
            netid_full = f"{netid_short.zfill(8)}"
            
            # Find provider
            provider_data = await find_provider_by_netid_async(netid_full)
            provider_address, provider_name, endpoint_sc = provider_data
            
            # Check SLA
            sla_data = await check_sla_async(
                netid_full,
                provider_address,
                provider_name,
                endpoint_sc
            )
            
            return {
                'netid': netid_short,
                'status': 'ok',
                'sla_state': sla_data['state'],
                'token_broker': sla_data['token'],
                'gateway_id': sla_data['gwid'],
                'provider_name': provider_name
            }
        except Exception as e:
            return {
                'netid': netid_short,
                'status': 'error',
                'message': str(e)
            }
    
    # Esegui tutti i check in parallelo
    tasks = [check_one_sla(netid) for netid in netids]
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    success_count = sum(1 for r in results if r['status'] == 'ok')
    
    print(f"✅ Batch completed: {success_count}/{len(netids)} successful in {total_time:.3f}s")
    
    return jsonify({
        'status': 'ok',
        'total': len(netids),
        'successful': success_count,
        'failed': len(netids) - success_count,
        'results': results,
        'total_time_ms': int(total_time * 1000),
        'avg_time_ms': int((total_time / len(netids)) * 1000)
    })

@app.route('/increment_counter', methods=['POST'])
def increment_counter():
    """Increment packet counter (already done by sla_check)"""
    print(f"📊 Incrementing counter for NetID: {request.json.get('netid')}")
    print(f"ℹ️  Counter incremented automatically by sla_check")
    return jsonify({'status': 'ok'})

@app.route('/get_sla_stats', methods=['POST'])
def get_sla_stats():
    """Get SLA statistics"""
    if not CONFIG['initialized']:
        return jsonify({'status': 'error', 'message': 'Not initialized'}), 400
    
    data = request.json
    netid_short = data['netid']
    type_op = data['type_op']
    
    netid_full = f"{netid_short.zfill(8)}"
    
    try:
        app_client_sc = bk.client.ApplicationClient(
            client=CONFIG['algod_client'],
            app=sla.app,
            app_id=CONFIG['sc_app_id'],
            sender=CONFIG['account'].address,
            signer=CONFIG['account'].signer,
        )
        
        result = app_client_sc.call(
            sla.get_sla_stats,
            NetID=netid_full,
            type_op=type_op,
            boxes=[(CONFIG['sc_app_id'], netid_full + type_op)]
        )
        
        return jsonify(result.return_value)
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/auto_config', methods=['GET'])
def auto_config():
    """Get auto-configuration from blockchain (with cache)"""
    if not CONFIG['initialized']:
        return jsonify({
            'status': 'error',
            'message': 'Service not initialized. Call /init first.'
        }), 400
    
    try:
        # Check cache first
        cached_config = cache_mgr.get_config('auto_config')
        if cached_config:
            print("✅ Auto-config from cache")
            return jsonify(cached_config)
        
        # Get from blockchain
        app_client_sc = bk.client.ApplicationClient(
            client=CONFIG['algod_client'],
            app=sla.app,
            app_id=CONFIG['sc_app_id'],
            sender=CONFIG['account'].address,
            signer=CONFIG['account'].signer,
        )
        
        # Get global state from my SC
        app_info = CONFIG['algod_client'].application_info(CONFIG['sc_app_id'])
        global_state = app_info['params']['global-state']
        
        # Decode global state
        import base64
        my_token = None
        my_gwid = None
        
        for item in global_state:
            key = base64.b64decode(item['key']).decode('utf-8')
            
            if key == 'Token_broker':
                my_token = base64.b64decode(item['value']['bytes']).decode('utf-8')
            elif key == 'GWid':
                my_gwid = base64.b64decode(item['value']['bytes']).decode('utf-8')
        
        print(f"\n{'='*60}")
        print(f"🔧 Auto-configuration loaded from blockchain:")
        print(f"   My NetID: {CONFIG['my_netid']}")
        print(f"   My Provider: {CONFIG['my_provider_name']}")
        print(f"   My Token: {my_token}")
        print(f"   My Gateway ID: {my_gwid}")
        print(f"{'='*60}")
        
        result = {
            'status': 'ok',
            'provider_name': CONFIG['my_provider_name'],
            'netid': CONFIG['my_netid'],
            'role': CONFIG['my_role'],
            'local_broker': 'tcp://localhost:1883',
            'foreign_broker': 'tcp://localhost:1884',
            'local_gateway_id': my_gwid,
            'token': my_token,
            'catalog_app_id': CONFIG['catalog_app_id'],
            'message': 'Configuration loaded from blockchain'
        }
        
        # Cache result
        cache_mgr.set_config('auto_config', result)
        
        return jsonify(result)
    
    except Exception as e:
        print(f"❌ Auto-config failed: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/cache/invalidate', methods=['POST'])
def invalidate_cache():
    """
    🆕 NEW: Invalidate cache manually
    
    Request body:
    {
        "type": "catalog|sla|config|all",
        "netid": "00000002"  // optional, for specific entries
    }
    """
    data = request.json
    cache_type = data.get('type', 'all')
    netid = data.get('netid')
    
    if cache_type == 'catalog':
        cache_mgr.invalidate_catalog(netid)
    elif cache_type == 'sla':
        if netid:
            cache_mgr.sla_cache.pop(netid, None)
        else:
            cache_mgr.sla_cache.clear()
    elif cache_type == 'config':
        cache_mgr.config_cache.clear()
    elif cache_type == 'all':
        cache_mgr.clear_all()
    
    return jsonify({
        'status': 'ok',
        'message': f'Cache {cache_type} invalidated'
    })

@app.route('/catalog/list', methods=['GET'])
def list_catalog():
    """
    🆕 NEW: List all providers in catalog
    """
    if not CONFIG['initialized']:
       return jsonify({
            'status': 'error',
            'message': 'Service not initialized'
        }), 400
    
    # Aggiorna index se necessario
    if catalog_index.needs_update():
        catalog_index.build_index(
            CONFIG['indexer_client'],
            CONFIG['catalog_app_id']
        )
    
    providers = catalog_index.get_all_providers()
    
    # Format output
    provider_list = []
    for netid, (address, name, endpoint) in providers.items():
        provider_list.append({
            'netid': netid,
            'address': address,
            'name': name,
            'endpoint': endpoint
        })
    
    return jsonify({
        'status': 'ok',
        'total': len(provider_list),
        'providers': provider_list,
        'index_age_seconds': int(time.time() - catalog_index.last_update)
    })

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 LoRaWAN Blockchain Service Starting (OPTIMIZED v3.0)...")
    print("="*60)
    print("⚡ Features:")
    print("   - Multi-level caching (Catalog, SLA, Config)")
    print("   - Local catalog indexing (O(1) lookups)")
    print("   - Async request handling")
    print("   - Thread pool executor (10 workers)")
    print("   - Batch SLA checking")
    print("="*60)
    app.run(host='0.0.0.0', port=5000, debug=True)
