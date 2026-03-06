FROM ubuntu:latest

# Imposta la variabile d'ambiente per non richiedere interazione durante l'installazione
ENV DEBIAN_FRONTEND=noninteractive

# Imposta la time zone
ENV TZ=Europe/Rome
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Crea la directory /run/mosquitto e imposta i permessi
RUN mkdir /run/mosquitto/ && chmod 777 /run/mosquitto/

# Installa le dipendenze
RUN apt-get update && apt-get install -y postgresql mosquitto nano net-tools iputils-ping wget curl software-properties-common build-essential tar ssh git screen mosquitto redis-server -y

# Aggiungi la chiave GPG e il repository di ChirpStack
RUN apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 1CE2AFD36DBCCA00
RUN echo "deb https://artifacts.chirpstack.io/packages/3.x/deb stable main" | tee /etc/apt/sources.list.d/chirpstack.list
RUN apt-get update

# Installa ChirpStack Network Server e Application Server
RUN apt-get install -y chirpstack-network-server chirpstack-application-server

# Download the Go 1.21.3 tarball
RUN wget https://go.dev/dl/go1.21.3.linux-amd64.tar.gz -O go1.21.3.linux-amd64.tar.gz

# Extract the tarball to /usr/local (installing Go)
RUN tar -C /usr/local -xzf go1.21.3.linux-amd64.tar.gz

# Remove the tarball to clear space
RUN rm go1.21.3.linux-amd64.tar.gz

# Set the Go binary path globally
ENV PATH="/usr/local/go/bin:${PATH}"
#ENV PATH="${PATH}:$(go env GOPATH)/bin"

# Installa statik e aggiorna il PATH
RUN go install github.com/rakyll/statik@latest
ENV PATH="${PATH}:/root/go/bin"

# Clona e installa LWN Simulator
RUN git clone https://github.com/UniCT-ARSLab/LWN-Simulator.git
WORKDIR /LWN-Simulator
# Modifica la porta in config.json da 8000 a 9000
RUN sed -i 's/"port":8000,/"port":9000,/' config.json
RUN make install-dep
RUN make build

# Copia i file di configurazione
COPY chirpstack-network-server.toml /etc/chirpstack-network-server/
COPY chirpstack-application-server.toml /etc/chirpstack-application-server/
COPY setup_postgresql.sh /root/
COPY entrypoint.sh /root/
COPY mosquitto.conf /etc/mosquitto/

# Esegui lo script di configurazione PostgreSQL
RUN chmod +x /root/setup_postgresql.sh && /root/setup_postgresql.sh

# Imposta lo script di avvio
RUN chmod +x /root/entrypoint.sh
ENTRYPOINT ["/root/entrypoint.sh"]
