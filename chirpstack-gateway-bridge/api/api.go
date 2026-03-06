package api

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	log "github.com/sirupsen/logrus"
)

var mqttClient mqtt.Client
var publishClients sync.Map
var publishClientsMutex sync.RWMutex

// HTTP client con timeout per chiamate blockchain
var httpClient = &http.Client{
	Timeout: 5 * time.Second, // IMPORTANTE: timeout di 5 secondi
	Transport: &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 100,
		IdleConnTimeout:     90 * time.Second,
		DisableKeepAlives:   false, // Riusa connessioni
	},
}

type Body struct {
	AddedBroker          string `json:"added_broker"`
	BrokerIPHNS          string `json:"broker_ip_h_ns"`
	GWIDToken            string `json:"gwid_token"`
	GWIDTokenForeign     string `json:"gwid_token_foreign"`
	BlockchainServiceURL string `json:"blockchain_service_url"`
	MyNetID              string `json:"my_netid"`
	MyProviderName       string `json:"my_provider_name"`
	IsForwarder          bool   `json:"is_forwarder"`
	AlgodAddress         string `json:"algod_address"`
	AlgodToken           string `json:"algod_token"`
	IndexerAddress       string `json:"indexer_address"`
	SCAppID              int    `json:"sc_app_id"`
	PrivateKeyMnemonic   string `json:"private_key_mnemonic"`
}

type SLACheckResponse struct {
	Status      string `json:"status"`
	SLAState    string `json:"sla_state"`
	TokenBroker string `json:"token_broker"`
	GatewayID   string `json:"gateway_id"`
	Message     string `json:"message"`
}

var (
	NsIpAddress          = ""
	AddedBroker          = ""
	GWid                 = ""
	GWidForeign          = ""
	GwidTopicName        = ""
	port                 = "3000"
	BlockchainServiceURL = ""
	BlockchainEnabled    = false
)

// checkSLAWithPythonService calls the Python blockchain service with timeout
func checkSLAWithPythonService(netID string) (*SLACheckResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	log.WithField("netid", netID).Debug("📞 Calling blockchain /check_sla")

	reqData := map[string]string{"netid": netID}
	reqDataJSON, _ := json.Marshal(reqData)

	req, err := http.NewRequestWithContext(
		ctx,
		"POST",
		BlockchainServiceURL+"/check_sla",
		bytes.NewBuffer(reqDataJSON),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to call blockchain service: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	log.WithFields(log.Fields{
		"netid":  netID,
		"status": resp.StatusCode,
	}).Debug("📥 Blockchain response")

	var slaResp SLACheckResponse
	if err := json.Unmarshal(body, &slaResp); err != nil {
		return nil, fmt.Errorf("failed to parse response: %w", err)
	}

	return &slaResp, nil
}

// incrementCounterWithPythonService increments packet counter (ASYNC)
func incrementCounterWithPythonService(netID string) {
	// Esegui in goroutine separata per non bloccare
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()

		log.WithField("netid", netID).Debug("📊 Calling blockchain /increment_counter")

		reqData := map[string]string{"netid": netID}
		reqDataJSON, _ := json.Marshal(reqData)

		req, err := http.NewRequestWithContext(
			ctx,
			"POST",
			BlockchainServiceURL+"/increment_counter",
			bytes.NewBuffer(reqDataJSON),
		)
		if err != nil {
			log.WithError(err).Warn("⚠️  Failed to create increment request")
			return
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := httpClient.Do(req)
		if err != nil {
			log.WithError(err).Warn("⚠️  Failed to increment counter")
			return
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			body, _ := io.ReadAll(resp.Body)
			log.WithFields(log.Fields{
				"netid":  netID,
				"status": resp.StatusCode,
				"body":   string(body),
			}).Warn("⚠️  Increment counter returned non-200")
			return
		}

		log.WithField("netid", netID).Debug("✅ Counter incremented")
	}()
}

// Launch starts the API
func Launch() func() error {
	return func() error {
		log.Info("🚀 Custom API module starting...")
		go startListener(port)
		return nil
	}
}

// startListener start a Listener on specified port to serve requests
func startListener(port string) {
	http.HandleFunc("/api/configure", handleRequest)
	http.HandleFunc("/api/health", healthCheck)
	log.Printf("API listening on port %s...\n", port)
	log.Fatal(http.ListenAndServe(fmt.Sprintf(":%s", port), nil))
}

// healthCheck returns API health status
func healthCheck(w http.ResponseWriter, r *http.Request) {
	response := map[string]interface{}{
		"status":             "ok",
		"blockchain_enabled": BlockchainEnabled,
		"gwid_local":         GWid,
		"gwid_foreign":       GWidForeign,
		"mqtt_broker":        AddedBroker,
	}
	jsonResponse, _ := json.Marshal(response)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write(jsonResponse)
}

// initMQTTClient initializes MQTT client with broker address
func initMQTTClient(brokerAddress string) {
	if brokerAddress == "" {
		log.Fatal("Indirizzo broker MQTT mancante")
		return
	}

	log.WithField("broker", brokerAddress).Info("🔌 Initializing MQTT client for API")

	clientOpts := mqtt.NewClientOptions().AddBroker(brokerAddress)
	clientOpts.SetAutoReconnect(true)
	clientOpts.SetCleanSession(true)
	clientOpts.SetClientID("ChirpStack_API_Custom")
	clientOpts.SetKeepAlive(60 * time.Second)
	clientOpts.SetPingTimeout(10 * time.Second)
	clientOpts.SetMaxReconnectInterval(10 * time.Second)

	mqttClient = mqtt.NewClient(clientOpts)

	if token := mqttClient.Connect(); token.Wait() && token.Error() != nil {
		log.WithError(token.Error()).Error("❌ Failed to connect to MQTT broker for API")
		return
	}

	log.Info("✅ API MQTT client connected")
}

// initPublishClient creates a persistent MQTT client for publishing
func initPublishClient(brokerAddress string, clientID string) mqtt.Client {
	if brokerAddress == "" {
		log.Error("❌ Broker address is empty")
		return nil
	}

	log.WithFields(log.Fields{
		"broker":    brokerAddress,
		"client_id": clientID,
	}).Info("🔌 Initializing publish client")

	opts := mqtt.NewClientOptions().
		AddBroker(brokerAddress).
		SetClientID(clientID).
		SetAutoReconnect(true).
		SetCleanSession(false).
		SetKeepAlive(60 * time.Second).
		SetPingTimeout(10 * time.Second).
		SetMaxReconnectInterval(10 * time.Second).
		SetWriteTimeout(5 * time.Second). // Timeout per scrittura
		SetConnectionLostHandler(func(client mqtt.Client, err error) {
			log.WithFields(log.Fields{
				"broker": brokerAddress,
				"error":  err,
			}).Warn("⚠️  Connection lost, will auto-reconnect")
		}).
		SetOnConnectHandler(func(client mqtt.Client) {
			log.WithField("broker", brokerAddress).Info("✅ Publish client reconnected")
		})

	client := mqtt.NewClient(opts)

	if token := client.Connect(); token.Wait() && token.Error() != nil {
		log.WithError(token.Error()).Error("❌ Failed to connect publish client")
		return nil
	}

	log.WithField("broker", brokerAddress).Info("✅ Publish client connected")
	return client
}

// getOrCreatePublishClient retrieves or creates a persistent MQTT client for a broker
func getOrCreatePublishClient(brokerAddress string) mqtt.Client {
	if client, ok := publishClients.Load(brokerAddress); ok {
		mqttClient := client.(mqtt.Client)
		if mqttClient.IsConnected() {
			return mqttClient
		}
		publishClients.Delete(brokerAddress)
	}

	publishClientsMutex.Lock()
	defer publishClientsMutex.Unlock()

	if client, ok := publishClients.Load(brokerAddress); ok {
		mqttClient := client.(mqtt.Client)
		if mqttClient.IsConnected() {
			return mqttClient
		}
	}

	clientID := fmt.Sprintf("MQTT_Forwarder_%d", time.Now().UnixNano())
	newClient := initPublishClient(brokerAddress, clientID)
	if newClient != nil {
		publishClients.Store(brokerAddress, newClient)
		log.WithField("broker", brokerAddress).Info("✅ New publish client created and cached")
	}
	return newClient
}

// handleRequest handles API POST requests
func handleRequest(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	var b Body
	if err := json.NewDecoder(r.Body).Decode(&b); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	log.WithFields(log.Fields{
		"added_broker": b.AddedBroker,
		"broker_h_ns":  b.BrokerIPHNS,
		"gwid_local":   b.GWIDToken,
		"gwid_foreign": b.GWIDTokenForeign,
		"blockchain":   b.BlockchainServiceURL,
	}).Info("📨 Received configuration request")

	NsIpAddress = b.BrokerIPHNS
	AddedBroker = b.AddedBroker
	GWid = b.GWIDToken
	GWidForeign = b.GWIDTokenForeign

	if GWidForeign == "" {
		GWidForeign = GWid
		log.Warn("⚠️  gwid_token_foreign not specified, using gwid_token")
	}

	GwidTopicName = b.GWIDToken

	if b.BlockchainServiceURL != "" {
		BlockchainServiceURL = b.BlockchainServiceURL

		log.WithField("url", BlockchainServiceURL).Info("🔗 Checking blockchain service")

		// Usa httpClient con timeout
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		req, err := http.NewRequestWithContext(ctx, "GET", BlockchainServiceURL+"/health", nil)
		if err != nil {
			log.WithError(err).Error("❌ Failed to create health check request")
			BlockchainEnabled = false
		} else {
			resp, err := httpClient.Do(req)
			if err != nil {
				log.WithError(err).Error("❌ Failed to connect to blockchain service")
				BlockchainEnabled = false
			} else {
				defer resp.Body.Close()
				body, _ := io.ReadAll(resp.Body)

				var healthResp map[string]interface{}
				if err := json.Unmarshal(body, &healthResp); err == nil {
					if initialized, ok := healthResp["initialized"].(bool); ok && initialized {
						log.WithFields(log.Fields{
							"provider": healthResp["my_provider"],
							"netid":    healthResp["my_netid"],
							"role":     healthResp["role"],
						}).Info("✅ Blockchain service is initialized")
						BlockchainEnabled = true
					} else {
						log.Warn("⚠️  Blockchain service is NOT initialized - call /init first!")
						BlockchainEnabled = false
					}
				} else {
					log.WithError(err).Error("❌ Failed to parse health response")
					BlockchainEnabled = false
				}
			}
		}
	} else {
		BlockchainEnabled = false
		log.Info("ℹ️  Blockchain service not configured")
	}

	log.WithFields(log.Fields{
		"ns_ip":        NsIpAddress,
		"gwid_local":   GWid,
		"gwid_foreign": GWidForeign,
		"topic":        GwidTopicName,
		"blockchain":   BlockchainEnabled,
	}).Info("✅ Configuration completed")

	initMQTTClient(AddedBroker)

	log.Info("🔌 Pre-initializing publish clients...")
	getOrCreatePublishClient(AddedBroker)
	if NsIpAddress != "" && NsIpAddress != AddedBroker {
		getOrCreatePublishClient(NsIpAddress)
	}

	response := map[string]string{
		"status":             "ok",
		"blockchain_enabled": fmt.Sprintf("%v", BlockchainEnabled),
	}
	jsonResponse, err := json.Marshal(response)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	jsonResponse = append(jsonResponse, []byte("\n")...)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	w.Write(jsonResponse)

	log.Info("🔔 Subscribing to MQTT topics...")
	go subscribeToTopic("gateway/+/event/up")
	go subscribeToTopic("gateway/+/event/stats")
	go subscribeToTopic("gateway/+/state/conn")
}

// onMessage handles incoming MQTT messages
func onMessage(client mqtt.Client, msg mqtt.Message) {
	payload := string(msg.Payload())

	log.WithFields(log.Fields{
		"topic":        msg.Topic(),
		"payload_size": len(payload),
	}).Debug("📬 Message received on MQTT")

	var payloadMap map[string]interface{}
	if err := json.Unmarshal([]byte(payload), &payloadMap); err != nil {
		log.WithError(err).Warn("❌ Failed to parse payload as JSON")
		return
	}

	isForeign := false
	targetGWid := GWid
	targetBroker := AddedBroker
	var netIDStr string

	topicParts := strings.Split(msg.Topic(), "/")
	if len(topicParts) < 2 {
		log.Warn("⚠️  Invalid topic format")
		return
	}

	topicName := topicParts[1]
	topicType := topicParts[len(topicParts)-1]
	newTopic := strings.Replace(msg.Topic(), topicName, GwidTopicName, 1)

	if topicType == "up" {
		log.WithField("topic", msg.Topic()).Debug("📨 Handling event UP")

		if payloadMap["phyPayload"] != nil {
			payloadPHY := payloadMap["phyPayload"].(string)
			decodedPhyPayload, err := base64.StdEncoding.DecodeString(payloadPHY)
			if err != nil {
				log.WithError(err).Error("❌ Failed to decode phyPayload")
				return
			}

			devAddr := getDevAddr(decodedPhyPayload)
			if devAddr == nil {
				log.Error("❌ Failed to extract DevAddr")
				return
			}

			netID := calculateNetID(devAddr)
			if netID == nil {
				log.Error("❌ Failed to calculate NetID")
				return
			}

			netIDStr = fmt.Sprintf("%02x", netID)
			log.WithField("netID", netIDStr).Debug("🔢 Calculated NetID")

			if netIDStr != "01" {
				isForeign = true
				log.WithField("netid", netIDStr).Debug("🌍 Foreign packet detected")

				if BlockchainEnabled {
					log.WithField("netid", netIDStr).Debug("🔗 Checking SLA")

					// Chiamata SLA con timeout
					slaResp, err := checkSLAWithPythonService(netIDStr)
					if err != nil {
						log.WithError(err).Warn("❌ SLA check failed - Using fallback")
						// Fallback invece di droppare
						targetGWid = GWidForeign
						targetBroker = NsIpAddress
					} else {
						log.WithFields(log.Fields{
							"netid": netIDStr,
							"state": slaResp.SLAState,
						}).Debug("📋 SLA check result")

						if slaResp.SLAState == "Accept" || slaResp.SLAState == "Active SLA" {
							if slaResp.GatewayID != "" && slaResp.GatewayID != "None" {
								targetGWid = slaResp.GatewayID
							} else {
								targetGWid = GWidForeign
							}

							if slaResp.TokenBroker != "" && slaResp.TokenBroker != "None" {
								if !strings.HasPrefix(slaResp.TokenBroker, "tcp://") {
									targetBroker = "tcp://" + slaResp.TokenBroker
								} else {
									targetBroker = slaResp.TokenBroker
								}
							} else {
								targetBroker = NsIpAddress
							}

							log.WithFields(log.Fields{
								"netid":      netIDStr,
								"gateway_id": targetGWid,
								"broker":     targetBroker,
							}).Debug("✅ SLA ACTIVE")

							// Incrementa counter in modo asincrono
							incrementCounterWithPythonService(netIDStr)
						} else {
							log.WithFields(log.Fields{
								"netid": netIDStr,
								"state": slaResp.SLAState,
							}).Warn("❌ SLA REJECTED - Dropping packet")
							return
						}
					}
				} else {
					targetGWid = GWidForeign
					targetBroker = NsIpAddress
				}

				log.WithFields(log.Fields{
					"netid":      netIDStr,
					"gateway_id": targetGWid,
					"broker":     targetBroker,
				}).Debug("✅ Foreign packet forwarding")
			}
		}
	} else if topicType == "stats" {
		log.WithField("topic", msg.Topic()).Debug("📊 Handling event STATS")
	} else if topicType == "conn" {
		log.WithField("topic", msg.Topic()).Debug("🔌 Handling state CONN")
	}

	decodedGWid, err := hex.DecodeString(targetGWid)
	if err != nil {
		log.WithError(err).Error("❌ Failed to decode target gateway ID")
		return
	}
	base64GWid := base64.StdEncoding.EncodeToString(decodedGWid)
	modifyMap(payloadMap, "gatewayID", base64GWid)

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		log.WithError(err).Error("❌ Failed to marshal payload")
		return
	}
	payload = string(payloadBytes)

	log.WithFields(log.Fields{
		"to_topic": newTopic,
		"broker":   targetBroker,
		"foreign":  isForeign,
	}).Debug("📤 Forwarding message")

	publishClient := getOrCreatePublishClient(targetBroker)
	if publishClient == nil {
		log.WithField("broker", targetBroker).Error("❌ Failed to get publish client")
		return
	}

	if !publishClient.IsConnected() {
		log.WithField("broker", targetBroker).Warn("⚠️  Client disconnected, attempting reconnection...")
		time.Sleep(100 * time.Millisecond)
		if !publishClient.IsConnected() {
			publishClients.Delete(targetBroker)
			publishClient = getOrCreatePublishClient(targetBroker)
			if publishClient == nil || !publishClient.IsConnected() {
				log.WithField("broker", targetBroker).Error("❌ Reconnection failed, dropping packet")
				return
			}
		}
	}

	// Pubblica con timeout
	token := publishClient.Publish(newTopic, 0, false, payload)
	if !token.WaitTimeout(2 * time.Second) {
		log.WithField("broker", targetBroker).Warn("⚠️  Publish timeout")
		return
	}
	if token.Error() != nil {
		log.WithError(token.Error()).Error("❌ Failed to publish message")
		return
	}

	log.WithFields(log.Fields{
		"topic":   newTopic,
		"broker":  targetBroker,
		"foreign": isForeign,
	}).Debug("✅ Message forwarded")
}

// subscribeToTopic subscribes to MQTT topic
func subscribeToTopic(topic string) {
	if mqttClient == nil {
		log.Error("❌ MQTT client not initialized")
		return
	}

	if !mqttClient.IsConnected() {
		log.Error("❌ MQTT client not connected")
		return
	}

	log.WithField("topic", topic).Info("🔔 Subscribing to topic")

	if token := mqttClient.Subscribe(topic, 0, onMessage); token.Wait() && token.Error() != nil {
		log.WithError(token.Error()).Fatal("❌ Failed to subscribe to topic")
	}

	log.WithField("topic", topic).Info("✅ Subscribed successfully")
}

// getDevAddr extracts DevAddr from physical payload
func getDevAddr(phyPayload []byte) []byte {
	if len(phyPayload) < 5 {
		log.WithField("length", len(phyPayload)).Error("❌ phyPayload too short")
		return nil
	}

	devAddr := make([]byte, 4)
	copy(devAddr, phyPayload[1:5])
	reverse(devAddr)
	return devAddr
}

// reverse reverses byte slice
func reverse[S ~[]E, E any](s S) {
	for i, j := 0, len(s)-1; i < j; i, j = i+1, j-1 {
		s[i], s[j] = s[j], s[i]
	}
}

// modifyMap recursively modifies map values
func modifyMap(payloadMap interface{}, key string, value string) {
	switch m := payloadMap.(type) {
	case map[string]interface{}:
		for k, v := range m {
			if k == key {
				m[k] = value
			} else {
				modifyMap(v, key, value)
			}
		}
	case []interface{}:
		for _, v := range m {
			modifyMap(v, key, value)
		}
	}
}

// calculateNetID calculates NetID from DevAddr
func calculateNetID(devAddr []byte) []byte {
	if len(devAddr) != 4 {
		log.WithField("length", len(devAddr)).Error("❌ Invalid DevAddr length")
		return nil
	}
	netID := devAddr[0] >> 1
	return []byte{netID}
}
