# Setup LoRaWAN Roaming System - CON Blockchain

Guida completa per testare il roaming LoRaWAN con gestione SLA automatizzata tramite Smart Contract Algorand.

---

## 🎯 Obiettivo

Sistema di roaming LoRaWAN dove i pacchetti foreign vengono inoltrati **solo se** esiste un SLA valido verificato su blockchain Algorand, con conteggio automatico pacchetti e pagamenti.

---

## 📦 1. Setup Container Docker

### Container Vodafone:

```bash
docker run -dit --restart unless-stopped \
  --name chirpstack_vodafone \
  -p 1883:1883 \
  -p 8080:8080 \
  -p 9000:9000 \
  chirpstack-complete
```

### Container Tim:

```bash
docker run -dit --restart unless-stopped \
  --name chirpstack_tim \
  -p 1884:1883 \
  -p 8081:8080 \
  -p 9001:9000 \
  chirpstack-complete
```

---

## ⛓️ 2. Setup Algorand Blockchain

### Avvia AlgoKit Localnet:

```bash
# Reset per blockchain pulita
algokit localnet reset

# Verifica status
algokit localnet status

# Dovresti vedere:
# algod - Running (porta 4001)
# indexer - Running (porta 8980)
```

### Verifica account e App ID:

```bash
algokit goal account list
```

**Output esempio:**
```
[online] JDITDA...NG4  [created app IDs: 1001]           # Catalog
[online] 4DPGK3...V2E  [created app IDs: 1049]           # Tim SC
[online] 7H25SL...TA4  [created app IDs: 1038]           # Vodafone SC
```

**Prendi nota di:**
- **Catalog App ID**: `1001`
- **Vodafone SC App ID**: `1038` (o più recente)
- **Tim SC App ID**: `1049` (o più recente)

### Esporta mnemonic:

```bash
# Account Vodafone (quello con App 1038)
algokit goal account export -a 7H25SL6MXCYZI5E6O6CVEZLDX3435E5DUBXJPXAHHBE7YPQLCYMOZFBTA4

# Account Tim (quello con App 1049)
algokit goal account export -a 4DPGK3ULDTFAPYNJC3RLNNEQYM2M6FFAMGKDQQ4ASBM3E3TEZFGGL27V2E
```

**Salva questi mnemonic!**

### Token Algorand:

```
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

---

## 🌐 3. Configurazione Gateway e Device

### Simulator Vodafone (http://localhost:9000):

**Gateway:**
```
Gateway EUI: 0000000000000001
Name: Gateway Vodafone
Gateway Bridge:
  - Address: localhost
  - Port: 1700
```

**Device Vodafone (locale):**
```
DevEUI: a000000000000001
DevAddr: 02000001
NwkSKey: 00000000000000000000000000000001
AppSKey: 00000000000000000000000000000001
AppKey: 00000000000000000000000000000000
Payload: 566F6461666F6E65
Active: ✅ YES
Send Interval: 10
```

**Device Tim (foreign):**
```
DevEUI: b000000000000002
DevAddr: 04000001
NwkSKey: 00000000000000000000000000000002
AppSKey: 00000000000000000000000000000002
AppKey: 00000000000000000000000000000000
Payload: 54696D
Active: ✅ YES
Send Interval: 10
```

---

## 🐍 4. Setup Python Blockchain Service

### File: `blockchain_service.py`

**Posizione:** `~/chirpstack-gateway-bridge/blockchain_service.py`

**Configurazione chiave (riga ~7):**

```python
PYTHON_SCRIPTS_PATH = os.path.expanduser('~/python_blockchain')
```

Verifica che punti alla directory con `_SC.py` e `_catalogo.py`.

### Avvia servizio:

```bash
# Attiva virtual environment
source ~/Downloads/blockchain/fork/PyTeal/2024_03_09/venv/bin/activate

# Vai nella directory
cd ~/chirpstack-gateway-bridge

# Avvia servizio (lascia terminale aperto per vedere log)
python3 blockchain_service.py
```

**Output atteso:**
```
✅ Imported Smart Contract modules from: ~/python_blockchain
* Running on http://0.0.0.0:5000
```

---

## 🔑 5. Inizializza Python Blockchain Service

### Terminal separato:

```bash
curl -X POST http://localhost:5000/init \
  -H "Content-Type: application/json" \
  -d '{
    "my_netid": "00000001",
    "my_provider_name": "Vodafone",
    "is_forwarder": true,
    "algod_address": "http://localhost:4001",
    "algod_token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "indexer_address": "http://localhost:8980",
    "sc_app_id": 1038,
    "private_key_mnemonic": "MNEMONIC_VODAFONE_DA_EXPORT"
  }'
```

**Sostituisci:**
- `sc_app_id`: App ID Vodafone (1038 o quello che hai)
- `private_key_mnemonic`: Il mnemonic esportato con `algokit goal account export`

**Risposta attesa:**
```json
{
  "status": "ok",
  "address": "7H25SL6MXCYZI5E6O6CVEZLDX3435E5DUBXJPXAHHBE7YPQLCYMOZFBTA4",
  "sc_app_id": 1038,
  "catalog_app_id": 1001,
  "my_netid": "00000001",
  "my_provider_name": "Vodafone",
  "role": "FORWARDER"
}
```

**⚠️ IMPORTANTE:** `catalog_app_id` deve essere **1001** (non null)!

### Verifica inizializzazione:

```bash
curl http://localhost:5000/health
```

**Deve mostrare:**
```json
{
  "status": "ok",
  "initialized": true,
  "my_netid": "00000001",
  "my_provider": "Vodafone",
  "role": "FORWARDER",
  "catalog_app_id": 1001
}
```

---

## 🌉 6. Compila e Avvia Gateway Bridge

### File: `api.go` (versione CON blockchain)

**Path:** `~/chirpstack-gateway-bridge/api/api.go`

**Caratteristiche versione blockchain:**
- ✅ Ha emoji nei log (📬📨🔗✅)
- ✅ Funzioni `checkSLAWithPythonService()` e `incrementCounterWithPythonService()`
- ✅ Logica: se NetID ≠ 01 → chiama blockchain → se Accept inoltra

### Compila:

```bash
cd ~/chirpstack-gateway-bridge
go build cmd/chirpstack-gateway-bridge/main.go
```

### Avvia:

```bash
./main -c packaging/files/chirpstack-gateway-bridge.toml --log-level 4
```

Lascia terminale aperto.

---

## ⚙️ 7. Configurazione Gateway Bridge CON Blockchain

```bash
curl -X POST http://localhost:3000/api/configure \
  -H "Content-Type: application/json" \
  -d '{
    "added_broker": "tcp://localhost:1883",
    "broker_ip_h_ns": "tcp://localhost:1884",
    "gwid_token": "0000000000000001",
    "blockchain_service_url": "http://localhost:5000",
    "my_netid": "00000001",
    "my_provider_name": "Vodafone",
    "is_forwarder": true
  }'
```

**Risposta attesa:**
```json
{"status":"ok","blockchain_enabled":"true"}
```

**⚠️ Se vedi `blockchain_enabled: false`:**
- Python service non attivo o non inizializzato
- Verifica: `curl http://localhost:5000/health`

---

## 📊 8. Verifica SLA tra Vodafone e Tim

### Opzione A - Via Python script:

```bash
source ~/Downloads/blockchain/fork/PyTeal/2024_03_09/venv/bin/activate
cd ~/python_blockchain
python3 deploy_SC_forwarder.py

# Menu:
# Option 11 - Confirm packet sending or SLA creation
# NetID: 00000002 (Tim)
```

**Output atteso:**
```
SLA Check Result: ['Active SLA', 'TIM_TOKEN', 'GW_TIM_001']
Forward SLA: ['00000002', 'Tim', 'Active SLA', 2000, 5, 0, 'TIM_TOKEN', 'GW_TIM_001']
```

Se vedi `State: Active SLA` → ✅ SLA esiste e è attivo!

### Opzione B - Via API:

```bash
curl -X POST http://localhost:5000/get_sla_stats \
  -H "Content-Type: application/json" \
  -d '{
    "netid": "00000002",
    "type_op": "_forward_box"
  }'
```

**Output:**
```
NetID:00000002|State:Active SLA|Count:0|Threshold:5|Price:2000
```

---

## ▶️ 9. Avvia Simulazione

**http://localhost:9000** → Click **▶️ Play**

---

## 🔍 10. Monitoring e Verifica

### Terminal 1 - Gateway Bridge Go:

**Device Vodafone (NetID 01):**
```
INFO 📍 Decoded DevAddr: 02000001
INFO 🔢 Calculated NetID: 01
INFO 🏠 NetID is homeNS (01) - Local packet
INFO ✅ Message forwarded → tcp://localhost:1884
```

**Device Tim (NetID 02) - CON BLOCKCHAIN:**
```
INFO 📍 Decoded DevAddr: 04000001
INFO 🔢 Calculated NetID: 02
INFO 🌍 NetID is foreign (not homeNS 01)
INFO 🔗 Blockchain ENABLED - Checking SLA
INFO 📞 Calling Python blockchain service /check_sla
INFO 📋 SLA check result:
  netid: 02
  state: Accept
  token: TIM_TOKEN
  gwid: GW_TIM_001
INFO ✅ SLA ACTIVE - Forwarding packet
INFO 📊 Calling /increment_counter
INFO ✅ Packet counter incremented
INFO ✅ Message forwarded → tcp://localhost:1884
```

---

### Terminal 2 - Python Blockchain Service:

```
============================================================
🔍 Checking SLA for NetID: 00000002
   My NetID: 00000001
   My Role: FORWARDER
============================================================
📞 Finding provider with NetID 00000002 in catalog...
🔍 Searching for NetID: '00000002' (length: 8)
   📋 Found NetID in catalog: '00000002' (length: 8)
   🔍 Comparing: '00000002' == '00000002' ? True
✅ MATCH! Returning provider
✅ Found provider:
   Address: 4DPGK3ULDTFAPYNJC3RLNNEQYM2M6FFAMGKDQQ4ASBM3E3TEZFGGL27V2E
   Name: Tim
   Endpoint: 1049
📡 Calling sla_check on Smart Contract...
✅ SLA Check Result:
   State: Accept
   Token: TIM_TOKEN
   Gateway ID: GW_TIM_001

📊 Incrementing counter for NetID: 00000002
ℹ️  Counter incremented automatically by sla_check
```

---

### Terminal 3 - Broker Tim (MQTT):

```bash
mosquitto_sub -h localhost -p 1884 -t "gateway/#" -v
```

Dovresti vedere:
```
gateway/0000000000000001/event/up {"phyPayload":"gAEAAAQACAAB..."}
```

---

### Verifica SLA Stats (in tempo reale):

```bash
# Ripeti questo comando ogni 30 secondi
curl -X POST http://localhost:5000/get_sla_stats \
  -H "Content-Type: application/json" \
  -d '{
    "netid": "00000002",
    "type_op": "_forward_box"
  }'
```

**Output:**
```
NetID:00000002|State:Active SLA|Count:3|Threshold:5|Price:2000
```

**Il Count incrementa ad ogni pacchetto inoltrato!** 📊

---

## 💰 11. Test Pagamento Automatico

Quando il counter raggiunge **threshold** (es: 5 pacchetti):

### Nel Python service vedrai:

```
⚠️ Threshold reached! Payment required
💰 Executing payment to Home NS...
✅ Payment successful
📊 Counter reset to 0
```

Oppure se il pagamento fallisce:
```
❌ Payment failed
⚠️ SLA state changed to: Banned
```

### Verifica su AlgoExplorer:

1. Vai su https://testnet.algoexplorer.io (o usa explorer locale)
2. Cerca l'address Vodafone: `7H25SL6MXCYZI5E6O6CVEZLDX3435E5DUBXJPXAHHBE7YPQLCYMOZFBTA4`
3. Vedrai transazioni:
   - Application calls a App 1038 (`sla_check`)
   - Inner transactions (payment quando raggiunge threshold)

---

## 🛠️ 12. Troubleshooting

### blockchain_enabled: false

**Causa:** Python service non raggiungibile.

**Fix:**
```bash
# Verifica Python service
curl http://localhost:5000/health

# Deve dire: "initialized": true, "catalog_app_id": 1001

# Se false o catalog null, reinizializza
pkill -f blockchain_service.py
python3 blockchain_service.py &
curl -X POST http://localhost:5000/init -d '{...}'
```

---

### Provider not found in catalog

**Causa:** Tim non registrato nel catalog o NetID sbagliato.

**Fix:**
```bash
source ~/Downloads/blockchain/fork/PyTeal/2024_03_09/venv/bin/activate
cd ~/python_blockchain
python3 deploy_SC_home.py

# Option 7 - Opt-in to catalog
# Option 9 - Register in catalog

# Option 5 - Complete catalog
# Verifica che Tim (NetID 00000002) sia presente
```

---

### SLA state: Reject

**Causa:** Parametri SLA incompatibili (prezzo/threshold).

**Fix:**
```bash
# Verifica parametri Smart Contract
python3 deploy_SC_forwarder.py
# Option 6 - Smart Contract initialization
# Imposta prezzo e threshold compatibili con Tim

python3 deploy_SC_home.py
# Option 6 - Smart Contract initialization
# Verifica che i parametri siano accettabili
```

**Condizioni per Accept:**
- `Tim.Price` ≤ `Vodafone.Price`
- `Vodafone.Threshold` ≥ `Tim.Threshold`

---

### Device Tim non trasmette

**Sintomo:** Vedi solo NetID 01 nei log, mai NetID 02.

**Fix:**
```bash
# Verifica nel Simulator (http://localhost:9000)
# Devices → Device_Tim → Active: ✅

# Oppure via JSON
docker exec -it chirpstack_vodafone cat /LWN-Simulator/lwnsimulator/devices.json | jq '.[] | select(.info.devAddr == "04000001") | .info.status.active'

# Deve dire: true
```

---

## 📋 13. Comandi Quick Start

```bash
# === BLOCKCHAIN ===
# 1. Start AlgoKit
algokit localnet start

# 2. Start Python blockchain service
cd ~/chirpstack-gateway-bridge
source ~/Downloads/blockchain/fork/PyTeal/2024_03_09/venv/bin/activate
python3 blockchain_service.py  # Lascia terminale aperto

# === TERMINAL SEPARATO ===
# 3. Initialize Python service
curl -X POST http://localhost:5000/init \
  -H "Content-Type: application/json" \
  -d '{
    "my_netid": "00000001",
    "my_provider_name": "Vodafone",
    "is_forwarder": true,
    "algod_address": "http://localhost:4001",
    "algod_token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "indexer_address": "http://localhost:8980",
    "sc_app_id": 1038,
    "private_key_mnemonic": "YOUR_VODAFONE_MNEMONIC"
  }'

# 4. Verify
curl http://localhost:5000/health
# Must show: "initialized": true, "catalog_app_id": 1001

# === CHIRPSTACK ===
# 5. Start containers
docker start chirpstack_vodafone chirpstack_tim
sleep 10

# === GATEWAY BRIDGE ===
# 6. Start Gateway Bridge
cd ~/chirpstack-gateway-bridge
./main -c packaging/files/chirpstack-gateway-bridge.toml --log-level 4  # Lascia aperto

# === TERMINAL SEPARATO ===
# 7. Configure Gateway Bridge
curl -X POST http://localhost:3000/api/configure \
  -H "Content-Type: application/json" \
  -d '{
    "added_broker": "tcp://localhost:1883",
    "broker_ip_h_ns": "tcp://localhost:1884",
    "gwid_token": "0000000000000001",
    "blockchain_service_url": "http://localhost:5000",
    "my_netid": "00000001",
    "my_provider_name": "Vodafone",
    "is_forwarder": true
  }'

# Should return: {"blockchain_enabled":"true","status":"ok"}

# 8. Monitor broker Tim (optional, terminal separato)
mosquitto_sub -h localhost -p 1884 -t "#" -v

# 9. Start simulation
# http://localhost:9000 → ▶️ Play
```

---

## ✅ 14. Checklist Completa

**Blockchain:**
- [ ] AlgoKit localnet running (verifica: `algokit localnet status`)
- [ ] Smart Contract Vodafone deployato (App ID: 1038 o più recente)
- [ ] Smart Contract Tim deployato (App ID: 1049 o più recente)
- [ ] Catalog deployato (App ID: 1001)
- [ ] Vodafone registrato nel catalog (NetID: 00000001)
- [ ] Tim registrato nel catalog (NetID: 00000002)
- [ ] Vodafone opted-in al catalog
- [ ] Tim opted-in al catalog
- [ ] Vodafone SC inizializzato (catalog ID, price, threshold, token, gwid)
- [ ] Tim SC inizializzato (catalog ID, price, threshold, token, gwid)

**Sistema:**
- [ ] Container Vodafone running
- [ ] Container Tim running
- [ ] Python blockchain_service.py running
- [ ] Python service inizializzato (health mostra initialized: true)
- [ ] Gateway Bridge compilato (versione con emoji)
- [ ] Gateway Bridge running
- [ ] Gateway Bridge configurato (blockchain_enabled: true)

**Simulator:**
- [ ] Gateway Vodafone creato (EUI: 0000000000000001)
- [ ] Device Vodafone (DevAddr: 02000001) - active ✅
- [ ] Device Tim (DevAddr: 04000001) - active ✅
- [ ] Simulazione avviata ▶️

**ChirpStack:**
- [ ] Gateway registrato in ChirpStack Vodafone (8080)
- [ ] Gateway registrato in ChirpStack Tim (8081)

---

## 🔄 15. Workflow Completo con Blockchain

```
1. Device Tim (NetID 02) trasmette
   ↓
2. Gateway Vodafone riceve (Simulator)
   ↓ UDP 1700
3. Gateway Bridge Standard → MQTT 1883
   ↓
4. Gateway Bridge Custom (api.go):
   ├─ Riceve da MQTT 1883
   ├─ Estrae DevAddr: 04000001
   ├─ Calcola NetID: 02 (foreign!)
   └─ Blockchain ENABLED
   ↓
5. HTTP POST http://localhost:5000/check_sla
   ↓
6. Python Blockchain Service:
   ├─ Converte "02" → "00000002"
   ├─ Cerca in Catalog (Indexer Algorand)
   ├─ Trova Tim (Endpoint: 1049)
   └─ Chiama Smart Contract Vodafone
   ↓
7. Smart Contract Algorand (on-chain):
   ├─ Verifica SLA esistente
   ├─ Se non esiste → Handshake con Tim SC
   ├─ Tim SC risponde (Accept/Reject)
   └─ Incrementa counter se Accept
   ↓
8. Risposta a Python Service → Gateway Bridge
   ↓
9. Se Accept:
   ├─ Inoltra pacchetto a MQTT 1884 (Tim)
   └─ Incrementa counter via /increment_counter
   ↓
10. ChirpStack Tim elabora pacchetto
    ↓
11. Ogni 5 pacchetti → Pagamento automatico!
```

---

## 📊 16. Monitoraggio Counter SLA

```bash
# Controlla ogni 30 secondi
watch -n 30 'curl -s -X POST http://localhost:5000/get_sla_stats \
  -H "Content-Type: application/json" \
  -d "{\"netid\": \"00000002\", \"type_op\": \"_forward_box\"}"'
```

Vedrai il Count incrementare:
```
Count:0 → Count:1 → Count:2 → ... → Count:5 → Count:0 (dopo pagamento)
```

---

## 🔑 17. Parametri Account Algorand

### Account Vodafone (Forwarder):

```
Address: 7H25SL6MXCYZI5E6O6CVEZLDX3435E5DUBXJPXAHHBE7YPQLCYMOZFBTA4
NetID: 00000001
Provider Name: Vodafone
SC App ID: 1038 (o più recente)
Role: FORWARDER

Export mnemonic:
algokit goal account export -a 7H25SL6MXCYZI5E6O6CVEZLDX3435E5DUBXJPXAHHBE7YPQLCYMOZFBTA4
```

### Account Tim (Home):

```
Address: 4DPGK3ULDTFAPYNJC3RLNNEQYM2M6FFAMGKDQQ4ASBM3E3TEZFGGL27V2E
NetID: 00000002
Provider Name: Tim
SC App ID: 1049 (o più recente)
Role: HOME

Export mnemonic:
algokit goal account export -a 4DPGK3ULDTFAPYNJC3RLNNEQYM2M6FFAMGKDQQ4ASBM3E3TEZFGGL27V2E
```

### Catalog:

```
App ID: 1001
Creator: JDITDANQSW7WTS33XVJZGYIC2JABLCJP67TV22DL3AB7QHAZQANVP5UNG4
```

---

## 📁 18. File Necessari

### Codice Go (versione con blockchain):

**File:** `~/chirpstack-gateway-bridge/api/api.go`

**Caratteristiche identificative:**
- Import: `"bytes"`, `"io"`, `"time"`
- Struct `SLACheckResponse`
- Funzioni: `checkSLAWithPythonService()`, `incrementCounterWithPythonService()`
- Log con emoji: 📬📨📍🔢🌍🔗✅❌
- Variabile globale: `BlockchainEnabled`

---

### Codice Python:

**File:** `~/chirpstack-gateway-bridge/blockchain_service.py`

**Endpoints:**
- `GET /` - Info servizio
- `GET /health` - Status
- `POST /init` - Inizializzazione
- `POST /check_sla` - Verifica SLA
- `POST /increment_counter` - Incrementa counter
- `POST /get_sla_stats` - Statistiche SLA

**Imports:**
```python
import _SC as sla
import _catalogo as ct
import beaker as bk
```

**Path configurabile (riga ~7):**
```python
PYTHON_SCRIPTS_PATH = os.path.expanduser('~/python_blockchain')
```

---

### Smart Contract Python:

**Directory:** `~/python_blockchain/`

**File necessari:**
- `_SC.py` - Smart Contract SLA
- `_catalogo.py` - Smart Contract Catalog
- `deploy_SC_forwarder.py` - Deploy e gestione Forwarder
- `deploy_SC_home.py` - Deploy e gestione Home
- `deploy_catalogo_by_LoRa.py` - Deploy e gestione Catalog

---

## 🔄 19. Stop/Restart Sistema Completo

### Stop:

```bash
# Gateway Bridge
pkill -f main

# Python service
pkill -f blockchain_service.py

# Containers
docker stop chirpstack_vodafone chirpstack_tim

# AlgoKit (opzionale)
algokit localnet stop
```

### Restart (ordine importante):

```bash
# 1. AlgoKit
algokit localnet start

# 2. Containers
docker start chirpstack_vodafone chirpstack_tim
sleep 15

# 3. Python service (terminal 1)
cd ~/chirpstack-gateway-bridge
source ~/Downloads/blockchain/fork/PyTeal/2024_03_09/venv/bin/activate
python3 blockchain_service.py

# === TERMINAL 2 ===
# 4. Initialize Python service
curl -X POST http://localhost:5000/init -d '{...}'

# 5. Start Gateway Bridge (terminal 3)
cd ~/chirpstack-gateway-bridge
./main -c packaging/files/chirpstack-gateway-bridge.toml --log-level 4

# === TERMINAL 4 ===
# 6. Configure Gateway Bridge
curl -X POST http://localhost:3000/api/configure -d '{...}'

# 7. Start simulation
# http://localhost:9000 → ▶️
```

---

## 📊 20. Porte Sistema Completo

| Servizio | Vodafone | Tim | Note |
|----------|----------|-----|------|
| MQTT Broker | 1883 | 1884 | Mosquitto |
| ChirpStack Web UI | 8080 | 8081 | Login: admin/admin |
| LWN Simulator | 9000 | 9001 | Web interface |
| Gateway Bridge API | 3000 | - | Solo Vodafone |
| Python Blockchain | 5000 | - | Flask REST API |
| Algorand Algod | 4001 | 4001 | Shared |
| Algorand Indexer | 8980 | 8980 | Shared |

---

## 🎯 21. Differenze Chiave vs Versione Senza Blockchain

### SENZA Blockchain:
- ✅ Pacchetti foreign sempre inoltrati (se modifichi api.go)
- ❌ Nessun controllo SLA
- ❌ Nessun conteggio pacchetti
- ❌ Nessun pagamento automatico
- ⚡ Più veloce (no chiamate HTTP/blockchain)

### CON Blockchain:
- ✅ Pacchetti foreign inoltrati **solo se SLA Accept**
- ✅ Verifica SLA on-chain (trustless)
- ✅ Conteggio pacchetti automatico
- ✅ Pagamento automatico al raggiungimento threshold
- ✅ Ban automatico se pagamento fallisce
- ⏱️ Latenza aggiuntiva ~50ms per chiamata blockchain

---

## 🚀 22. Scenario Test Completo

1. **Avvia tutto** (AlgoKit + Containers + Python + Gateway Bridge)
2. **Inizializza** blockchain service
3. **Configura** Gateway Bridge con blockchain
4. **Avvia** simulazione
5. **Monitora** log per vedere SLA check
6. **Aspetta** 5 pacchetti per vedere pagamento automatico
7. **Verifica** su AlgoExplorer le transazioni on-chain
8. **Testa** ban modificando saldo account per far fallire pagamento

---

**Fine Report - Versione CON Blockchain**

**Sistema Production-Ready per Roaming LoRaWAN Decentralizzato!** 🎊⛓️✨
