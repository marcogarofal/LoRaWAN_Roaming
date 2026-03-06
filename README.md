# LoRaWAN Roaming System with Blockchain SLA

A complete LoRaWAN roaming system with automated SLA management via Smart Contracts on the Algorand blockchain. When a device from a foreign network is detected, the system verifies a valid SLA on-chain before forwarding the packet, with automatic packet counting and payment settlement.

---

## 📐 Architecture

```
Device LoRaWAN / LWN Simulator
    ↓ UDP 1700
ChirpStack Gateway Bridge (standard)
    ↓ publishes MQTT → localhost:1883
Mosquitto MQTT Broker (in Docker container)
    ↓ subscribed by
Custom Gateway Bridge (Go) — api.go
    ├─ Extracts DevAddr → Calculates NetID
    ├─ If NetID == homeNS → forward directly
    └─ If NetID ≠ homeNS (foreign packet):
         └─ HTTP → Python Blockchain Service (Flask)
              └─ Algorand Smart Contract
                   ├─ Accept → forward + increment counter
                   └─ Reject → drop packet
```

### NetID / DevAddr Mapping

The first byte of `DevAddr` encodes the NetID: `first_byte = NetID * 2`

| NetID | First byte (hex) | Example DevAddr |
|-------|-----------------|-----------------|
| 01    | 02              | `02000001`      |
| 02    | 04              | `04000001`      |
| 03    | 06              | `06000001`      |

### SLA Lifecycle

When a foreign packet arrives for the first time, the Forwarder SC initiates a handshake with the Home SC. Once the SLA is active, every forwarded packet increments a counter. When the counter reaches the configured threshold, an automatic on-chain payment is triggered. If the payment fails, the SLA transitions to **Banned** state.

---

## 📁 Repository Structure

```
.
├── README.md                        # This file
├── auto_deploy.py                   # Automated blockchain deployment script
├── config_deploy.yaml               # Configuration for auto_deploy.py
├── blockchain_service.py            # Python Flask service — Algorand bridge
│
├── Chirpstack_BackEnd/              # Docker setup for ChirpStack + Mosquitto
│   └── README.md                    # Backend-specific setup guide
│
├── chirpstack-gateway-bridge/       # Custom Go Gateway Bridge
│   ├── api/
│   │   └── api.go                   # Core logic: NetID routing + blockchain calls
│   ├── cmd/chirpstack-gateway-bridge/
│   ├── packaging/files/
│   │   └── chirpstack-gateway-bridge.toml
│   └── main                         # Compiled binary
│
└── smart_contracts/                 # Algorand Smart Contracts (PyTeal/Beaker)
    └── README.md                    # Smart contract setup and deploy guide
```

---

## ✅ Prerequisites

| Tool | Purpose | Min Version |
|------|---------|-------------|
| Docker | ChirpStack backend | any |
| Go | Gateway Bridge | 1.18+ |
| Python | Blockchain service + Smart Contracts | 3.12+ |
| AlgoKit | Algorand localnet | latest |
| Git | Clone repo | any |

### Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask beaker-pyteal py-algorand-sdk pyyaml prettytable
```

---

## 🚀 Setup & Run

> **Note:** The Smart Contracts must already be deployed and configured before starting. See [`smart_contracts/README.md`](smart_contracts/README.md) for deployment instructions. The `auto_deploy.py` script can automate that step.

### Step 1 — Start Algorand Localnet

```bash
algokit localnet reset     # clean state
algokit localnet status    # verify algod:4001 and indexer:8980 are running
```

---

### Step 2 — Start ChirpStack Backend

See [`Chirpstack_BackEnd/README.md`](Chirpstack_BackEnd/README.md) for full details.

```bash
cd Chirpstack_BackEnd

# Build image (first time only)
docker build -t chirpstack-complete .

# Vodafone container (NetID 01)
docker run -dit --restart unless-stopped \
  --name chirpstack_vodafone \
  -p 1883:1883 \
  -p 8080:8080 \
  -p 9000:9000 \
  chirpstack-complete

# Tim container (NetID 02)
docker run -dit --restart unless-stopped \
  --name chirpstack_tim \
  -p 1884:1883 \
  -p 8081:8080 \
  -p 9001:9000 \
  chirpstack-complete
```

Wait ~15 seconds for services to start, then verify:

```bash
docker exec -it chirpstack_vodafone screen -ls
# Should show: mqtt, network-server, application-server, lwn-simulator
```

---

### Step 3 — Start Python Blockchain Service

```bash
source venv/bin/activate
python3 blockchain_service.py
```

Expected output:
```
✅ Imported Smart Contract modules from: ./smart_contracts/
* Running on http://0.0.0.0:5000
```

Leave this terminal open.

---

### Step 4 — Initialize Python Blockchain Service

In a new terminal, initialize the service with the Vodafone (Forwarder) identity:

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
    "sc_app_id": <VODAFONE_SC_APP_ID>,
    "private_key_mnemonic": "<VODAFONE_MNEMONIC>"
  }'
```

Replace `<VODAFONE_SC_APP_ID>` and `<VODAFONE_MNEMONIC>` with the values from your deployment (see `config_deploy_deployed.json`).

Verify initialization:

```bash
curl http://localhost:5000/health
```

Expected:
```json
{
  "status": "ok",
  "initialized": true,
  "my_netid": "00000001",
  "my_provider": "Vodafone",
  "role": "FORWARDER",
  "catalog_app_id": <CATALOG_APP_ID>
}
```

> ⚠️ `catalog_app_id` must not be null. If it is, the SC was not properly initialized — check `smart_contracts/README.md`.

---

### Step 5 — Build and Start Gateway Bridge

```bash
cd chirpstack-gateway-bridge

# Compile (only needed if you modified api.go)
go build cmd/chirpstack-gateway-bridge/main.go

# Start
./main -c packaging/files/chirpstack-gateway-bridge.toml --log-level 4
```

Expected output:
```
INFO 🚀 Custom API module starting...
INFO API listening on port 3000...
INFO backend/semtechudp: starting gateway udp listener addr="0.0.0.0:1700"
INFO integration/mqtt: connected to mqtt broker
```

Leave this terminal open.

---

### Step 6 — Configure Gateway Bridge

#### With Blockchain (recommended):

```bash
curl -X POST http://localhost:3000/api/configure \
  -H "Content-Type: application/json" \
  -d '{
    "added_broker": "tcp://localhost:1883",
    "broker_ip_h_ns": "tcp://localhost:1884",
    "gwid_token": "0000000000000001",
    "gwid_token_foreign": "0000000000000001",
    "blockchain_service_url": "http://localhost:5000",
    "my_netid": "00000001",
    "my_provider_name": "Vodafone",
    "is_forwarder": true
  }'
```

Expected: `{"status":"ok","blockchain_enabled":"true"}`

#### Without Blockchain (simple forwarding):

```bash
curl -X POST http://localhost:3000/api/configure \
  -H "Content-Type: application/json" \
  -d '{
    "added_broker": "tcp://localhost:1883",
    "broker_ip_h_ns": "tcp://localhost:1884",
    "gwid_token": "0000000000000001"
  }'
```

Expected: `{"status":"ok","blockchain_enabled":"false"}`

---

### Step 7 — Configure LWN Simulator

Open **http://localhost:9000** (Vodafone simulator).

**Gateway Bridge section:**
- Address: `localhost`
- Port: `1700`
→ Save

**Gateways → Create Gateway:**

| Field | Value |
|-------|-------|
| Gateway EUI | `0000000000000001` |
| Name | `Gateway Vodafone` |

**Devices → Create Device (Vodafone — local, NetID 01):**

| Field | Value |
|-------|-------|
| Device EUI | `a000000000000001` |
| DevAddr | `02000001` |
| NwkSKey | `00000000000000000000000000000001` |
| AppSKey | `00000000000000000000000000000001` |
| Payload (hex) | `566F6461666F6E65` ("Vodafone") |
| Send Interval | `10` |
| Active | ✅ |
| Base64 | ❌ |

**Devices → Create Device (Tim — foreign, NetID 02):**

| Field | Value |
|-------|-------|
| Device EUI | `b000000000000002` |
| DevAddr | `04000001` |
| NwkSKey | `00000000000000000000000000000002` |
| AppSKey | `00000000000000000000000000000002` |
| Payload (hex) | `54696D` ("Tim") |
| Send Interval | `10` |
| Active | ✅ |
| Base64 | ❌ |

Click **▶️ Play** — status should turn 🟢.

---

### Step 8 — Register Gateway in ChirpStack

Open **http://localhost:8080** → login `admin/admin`

Go to **Gateways → Create**:
- Gateway ID: `0000000000000001`
- Name: `Gateway Vodafone`
- Select available network server

The gateway should show 🟢 Online within a few seconds.

---

## 🔍 Monitoring

### Gateway Bridge logs (terminal where `./main` is running)

**Local packet (Vodafone device, NetID 01):**
```
INFO 📍 Decoded DevAddr: 02000001
INFO 🔢 Calculated NetID: 01
INFO 🏠 NetID is homeNS (01) - Local packet
INFO ✅ Message forwarded → tcp://localhost:1884
```

**Foreign packet (Tim device, NetID 02) with blockchain:**
```
INFO 📍 Decoded DevAddr: 04000001
INFO 🔢 Calculated NetID: 02
INFO 🌍 NetID is foreign (not homeNS 01)
INFO 🔗 Blockchain ENABLED - Checking SLA
INFO 📋 SLA check result: state=Accept token=TIM_TOKEN gwid=GW_TIM_001
INFO ✅ SLA ACTIVE - Forwarding packet
INFO 📊 Packet counter incremented
INFO ✅ Message forwarded → tcp://localhost:1884
```

### Python Blockchain Service logs

```
🔍 Checking SLA for NetID: 00000002
✅ Found provider: Tim (Endpoint: <APP_ID>)
📡 Calling sla_check on Smart Contract...
✅ SLA Check Result: Accept
📊 Counter incremented
```

### Monitor SLA counter in real time

```bash
watch -n 10 'curl -s -X POST http://localhost:5000/get_sla_stats \
  -H "Content-Type: application/json" \
  -d "{\"netid\": \"00000002\", \"type_op\": \"_forward_box\"}"'
```

Output: `NetID:00000002|State:Active SLA|Count:3|Threshold:5|Price:2000`

When `Count` reaches `Threshold`, an automatic on-chain payment is triggered and the counter resets to 0.

### Monitor MQTT broker (Tim side)

```bash
mosquitto_sub -h localhost -p 1884 -t "gateway/#" -v
```

---

## 🔌 Port Reference

| Service | Vodafone | Tim | Notes |
|---------|----------|-----|-------|
| MQTT Broker | 1883 | 1884 | Mosquitto |
| ChirpStack Web UI | 8080 | 8081 | admin/admin |
| LWN Simulator | 9000 | 9001 | Web UI |
| Gateway Bridge API | 3000 | — | Config + health |
| Python Blockchain | 5000 | — | Flask REST |
| Gateway Bridge UDP | 1700 | — | Semtech UDP |
| Algorand Algod | 4001 | shared | |
| Algorand Indexer | 8980 | shared | |

---

## 🔁 Stop / Restart

### Stop all services

```bash
pkill -f main                          # Gateway Bridge
pkill -f blockchain_service.py         # Python service
docker stop chirpstack_vodafone chirpstack_tim
algokit localnet stop                  # optional
```

### Restart (order matters)

```bash
# 1. Algorand
algokit localnet start

# 2. Docker containers
docker start chirpstack_vodafone chirpstack_tim
sleep 15

# 3. Python service (terminal 1)
source venv/bin/activate
python3 blockchain_service.py

# 4. Initialize (terminal 2)
curl -X POST http://localhost:5000/init -H "Content-Type: application/json" -d '{...}'

# 5. Gateway Bridge (terminal 3)
cd chirpstack-gateway-bridge
./main -c packaging/files/chirpstack-gateway-bridge.toml --log-level 4

# 6. Configure Gateway Bridge (terminal 2)
curl -X POST http://localhost:3000/api/configure -H "Content-Type: application/json" -d '{...}'

# 7. Start simulation: http://localhost:9000 → ▶️
```

---

## 📚 References

- [ChirpStack Documentation](https://www.chirpstack.io/docs/)
- [Chirpstack BackEnd GitHub](https://github.com/lucadagati/Chirpstack_BackEnd)
- [Chirpstack gateway-bridge GitHub](https://github.com/lucadagati/chirpstack-gateway-bridge/tree/v3)
- [Algorand Developer Docs](https://developer.algorand.org/)
- [AlgoKit Documentation](https://developer.algorand.org/docs/get-started/algokit/)
- [LWN Simulator GitHub](https://github.com/UniCT-ARSLab/LWN-Simulator)


