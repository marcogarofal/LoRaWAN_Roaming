#!/bin/bash

# Avvia il servizio PostgreSQL
service postgresql start

# Attendi che PostgreSQL sia pronto (potrebbe essere necessario regolare il tempo di attesa)
sleep 10

# Configura il database per ChirpStack Application Server
su - postgres -c "psql -c \"CREATE ROLE chirpstack_as WITH LOGIN PASSWORD 'dbpassword';\""
su - postgres -c "psql -c \"CREATE DATABASE chirpstack_as WITH OWNER chirpstack_as;\""
su - postgres -c "psql -d chirpstack_as -c \"CREATE EXTENSION pg_trgm; CREATE EXTENSION hstore;\""

# Configura il database per ChirpStack Network Server
su - postgres -c "psql -c \"CREATE ROLE chirpstack_ns WITH LOGIN PASSWORD 'dbpassword';\""
su - postgres -c "psql -c \"CREATE DATABASE chirpstack_ns WITH OWNER chirpstack_ns;\""

# Avvia i servizi chirpstack
#service chirpstack-network-server start
#service chirpstack-application-server start
