# SLA Success Scenario - Compatible Values


## Overview

**Vodafone** and **Tim** are identifier names used in this guide to represent two different network operators/providers in the LoRaWAN roaming scenario. These names are used purely as examples to demonstrate the interaction between two distinct providers in the system.

---



## Installation and Configuration Guide

### Algokit Installation

0. Create and manage virtual environment:
```bash
mkdir venv
python3 -m venv venv/
```

Activate virtual environment:
```bash
source venv/bin/activate
```

1. Install Algokit using `pipx`:
```bash
pipx install algokit
```

2. Verify `algokit` version:
```bash
algokit --version
```

3. Initialize project with `algokit`:
```bash
algokit init
```

4. Reset Algokit local network:
```bash
algokit localnet reset
```

5. Start Algokit local network:
```bash
algokit localnet start
algokit explore
```

### Dependencies Installation

6. Install `beaker-pyteal`:
```bash
pip install beaker-pyteal
```

7. Update `setuptools`:
```bash
pip install --upgrade setuptools
```

8. Install `setuptools` and `pkg_resources`:
```bash
pip install setuptools pkg_resources
```

9. Update `setuptools` and `wheel`:
```bash
pip install --upgrade setuptools wheel
```

10. Install `prettytable`:
```bash
pip install prettytable
```

### Project Structure

```
project/
├── _SC.py                         # Smart Contract SLA
├── _catalogo.py                   # Smart Contract Catalog
├── deploy_catalogo_by_lora.py     # LoRa Manager (EXECUTABLE)
├── deploy_SC_forwarder.py         # Vodafone Provider (EXECUTABLE)
└── deploy_SC_home.py              # Tim Provider (EXECUTABLE)
```












------------------------------------------
------------------------------------------

## PHASE 0:
```bash
python3 _catalogo.py
```

1. Compiles the Catalog smart contract
   - Note the **App ID** (example: 1001)
2. Generates TEAL bytecode and metadata files
3. Exports artifacts to ./catalogo/artifacts/


```bash
python3 _SC.py
```
1. Compiles the SLA smart contract
2. Generates TEAL bytecode and metadata files
3. Exports artifacts to ./SC/artifacts/




## PHASE 1: LoRa Manager Setup (Catalog)

### 1. Start LoRa Manager
```bash
python3 deploy_catalogo_by_lora.py
```

**Operations:**
1. **Option 1**: Deploy catalog app
   - Note the **App ID** (example: 1001)
2. **Option 3**: Verify application info
3. **Option 4**: Verify account balance

**Expected output:**
```
Deployed catalog app in txid XXX
App ID: 1001
Address: XXXXXXXXXX
```

---

## PHASE 2: Vodafone Provider Setup (Forwarder)

### 2. Start Vodafone Provider
```bash
python3 deploy_SC_forwarder.py
```

**Configuration for SUCCESS:**

1. **Option 1**: Deploy SLA Smart Contract
2. **Option 6**: Smart Contract initialization
   ```
   Enter the catalog endpoint: 1001
   Enter the price for each SLA (mALGO): 2000
   Enter the minimum number of packets for each SLA: 5
   Enter the minimum percentage of packets that cannot be lost for each SLA (%): 80
   Enter the token: VODAFONE_TOKEN
   Enter the gateway id: GW_VODAFONE_001
   ```

3. **Option 7**: Opt-in to catalog
4. **Option 9**: Register in the catalog

**Note the Vodafone Smart Contract App ID** (example: 1002)

---

## PHASE 3: Tim Provider Setup (Home)

### 3. Start Tim Provider
```bash
python3 deploy_SC_home.py
```

**COMPATIBLE Configuration:**

1. **Option 1**: Deploy SLA Smart Contract
2. **Option 6**: Smart Contract initialization (COMPATIBLE VALUES)
   ```
   Enter the catalog endpoint: 1001
   Enter the price for each SLA (mALGO): 3000        ← HIGHER than Vodafone (2000)
   Enter the minimum number of packets for each SLA: 3   ← LOWER than Vodafone (5)
   Enter the minimum percentage of packets that cannot be lost for each SLA (%): 75
   Enter the token: TIM_TOKEN
   Enter the gateway id: GW_TIM_001
   ```

3. **Option 7**: Opt-in to catalog
4. **Option 9**: Register in the catalog

**Note the Tim Smart Contract App ID** (example: 1003)

---

## PHASE 4: Setup Verification

### 4. From LoRa Manager
```bash
# Return to LoRa Manager (deploy_catalogo_by_lora.py)
```

**Verifications:**
- **Option 5**: Complete catalog
  ```
  +----------+--------+---------------+---------------------------+
  | Address  | NetID  | Provider Name | Endpoint of Smart Contract|
  +----------+--------+---------------+---------------------------+
  | ADDR_VF  |00000001|   Vodafone    |           1002            |
  | ADDR_TIM |00000002|     Tim       |           1003            |
  +----------+--------+---------------+---------------------------+
  ```

- **Option 6**: Test NetID search
  - Enter: `00000001` → Should find Vodafone
  - Enter: `00000002` → Should find Tim

---

## PHASE 5: Successful SLA Creation Test

### 5. SLA Creation (Vodafone → Tim)
```bash
# On Vodafone Provider (deploy_SC_forwarder.py)
```

**Test:**
- **Option 11**: Confirm packet sending or SLA creation
  - Enter NetID: `00000002`

**EXPECTED Output (SUCCESS):**
```
Address: ADDR_TIM
Provider name: Tim
Smart Contract Endpoint: 1003
['Accept', 'TIM_TOKEN', 'GW_TIM_001']
SLA {00000002_forward_box} created successfully
```

### 6. Verify SLA Created on Vodafone
```bash
# On Vodafone Provider
```

- **Option 13**: View SLA (forwarder side)
  - Enter NetID: `00000002`

**Expected output:**
```
['00000002', 'Tim', 'Active SLA', 2000, 5, 0, 'TIM_TOKEN', 'GW_TIM_001']
```

### 7. Verify SLA Created on Tim
```bash
# On Tim Provider (deploy_SC_home.py)
```

- **Option 12**: View SLA (home side)
  - Enter NetID: `00000001`

**Expected output:**
```
['00000001', 'Vodafone', 'Active SLA', 2000, 5, 0, 'TIM_TOKEN', 'GW_TIM_001']
```

---

## PHASE 6: Traffic Simulation and Payments

### 8. Test Packet Sending (from Vodafone to Tim)
```bash
# On Vodafone Provider (deploy_SC_forwarder.py)
```

**Packet simulation:**
- **Option 11**: Confirm packet sending (repeat 5 times)
  - Enter NetID: `00000002`
  - Each time should respond: `['Accept', 'TIM_TOKEN', 'GW_TIM_001']`

### 9. Packet Reception on Tim
```bash
# On Tim Provider (deploy_SC_home.py)
```

**For each received packet:**
- **Option 14**: Received a packet, increment counter
  - Enter NetID: `00000001`
  - Output: `Packet received`

**Verify counter:**
- **Option 12**: View SLA (home side)
  - Counter should increment: `[..., ..., 'Active SLA', 2000, 5, 1, ...]` → `[..., 2, ...]` → etc.

### 10. Test Automatic Payment
```bash
# On Tim Provider
```

When the counter reaches the threshold (5 packets):
- **Option 14**: Last packet → Triggers automatic payment
- **Option 12**: Verify SLA → Counter reset to 0

**Verify balances:**
- **Option 3**: Application info → Tim's balance should increase
- On Vodafone **Option 3** → Balance should decrease by 2000 mALGO

---

## PHASE 7: Advanced Functions Test

### 11. Test Bidirectional SLA (Tim → Vodafone)
```bash
# On Tim Provider (deploy_SC_home.py)
```

- **Option 11**: Confirm packet sending
  - Enter NetID: `00000001`
  - Should create a new SLA in the opposite direction

### 12. Test Ban Provider
```bash
# On Tim Provider
```

- **Option 15**: Ban a provider
  - Enter NetID: `00000001`
  - SLA state becomes: `'Banned'`

---

## Compatible Values Logic

### Configured Parameters

| Provider | Max Price | Min Threshold | Negotiation |
|----------|-----------|---------------|-------------|
| **Vodafone** | 2000 mALGO | 5 packets | Proposes: 2000/5 |
| **Tim** | 3000 mALGO | 3 packets | Accepts if: ≤3000 and ≥3 |

### Success Conditions

```
✅ Vodafone Price (2000) ≤ Tim Max Price (3000)
✅ Vodafone Threshold (5) ≥ Tim Min Threshold (3)
→ ACTIVE SLA
```

### If You Configure Incompatible Values

```python
# FAILURE EXAMPLE:
Vodafone: price=5000, threshold=2
Tim: max_price=3000, min_threshold=5

❌ 5000 > 3000 (price too high)
❌ 2 < 5 (threshold too low)
→ SLA REJECTED
```

## Expected Success Output

Upon completion, you should see:

1. **Populated catalog** with 2 providers
2. **Active SLA** between Vodafone and Tim
3. **Automatic payments** every 5 packets
4. **Token and Gateway ID** correctly assigned
5. **Counters** that reset after payments

This scenario simulates a realistic LoRaWAN roaming where providers automatically negotiate SLAs with economically compatible parameters.
