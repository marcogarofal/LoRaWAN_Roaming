# ChirpStack_BackEnd

This repository is designed to facilitate the deployment of the ChirpStack LoRaWAN network server and its associated services through Docker. The setup includes the ChirpStack Network Server, ChirpStack Application Server, PostgreSQL, Mosquitto MQTT broker, and Redis, providing a comprehensive backend for managing LoRaWAN devices and data.

## Prerequisites

Before you begin, ensure you have the following tools installed on your machine:

- **Docker**: Essential for creating and managing your containerized applications.
- **Git**: Required if you plan to clone the repository. If not, you can simply download the repository files.

## Installation

Follow these steps to get your ChirpStack_BackEnd up and running:

### Cloning the Repository (Optional)

If you prefer to use Git to manage your projects, you can clone this repository using the following command:

```bash
git clone https://github.com/lucadagati/Chirpstack_BackEnd.git
cd Chirpstack_BackEnd
```

### Building the Docker Container
Build the Docker image with the following command:

```bash
docker build -t chirpstack-complete .
```
This command creates a Docker image named chirpstack-backend. You can replace `chirpstack-backend` with any name you prefer for your Docker image.

### Starting the Container
To start the container, use:

```bash
docker run -dit --restart unless-stopped --name chirpstack chirpstack-complete
```
Replace `chirpstack-backend-instance` with your desired container name. This command runs your Docker container in detached mode, ensures it restarts unless manually stopped, and names it for easier management.

## Configuration
The deployment requires configuration of the ChirpStack Network Server and Application Server. You can find the configuration files at:

/etc/chirpstack-network-server/chirpstack-network-server.toml
/etc/chirpstack-application-server/chirpstack-application-server.toml
Edit these files according to your network specifications and requirements.

## Usage
Once your container is up and running, you can interact with the ChirpStack servers and other services:

Accessing the Web Interface: The ChirpStack Application Server web interface is accessible at http://localhost:8080 (default port).
MQTT Broker: The Mosquitto MQTT broker is configured to allow anonymous access and listens on the standard port 1883.
Logs: To view logs for debugging, you can use Docker's log command: docker logs chirpstack-backend-instance.

## Support and Contributions
If you encounter any issues or have suggestions for improvements, please submit an issue or pull request on GitHub. For more direct support, consider reaching out to the project maintainers via GitHub or the project's official communication channels.
