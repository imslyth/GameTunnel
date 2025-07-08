# GameTunnel - Network Optimization for Gaming

A high-performance network tunneling solution designed to reduce gaming latency by routing traffic through optimized servers, similar to FlowPing.

## Features

- **Smart Routing**: Automatically selects the best server path to minimize latency
- **Real-time Monitoring**: Live dashboard showing ping times, packet loss, and connection quality
- **Multiple Server Locations**: Support for multiple relay servers worldwide
- **Game Detection**: Automatic detection and optimization for popular games
- **Traffic Encryption**: Secure tunneling with encryption
- **Bandwidth Optimization**: Intelligent traffic shaping and compression

## Components

### 1. Tunnel Client (`client/`)
- Routes game traffic through optimized tunnel servers
- Automatic server selection based on latency
- Real-time connection monitoring
- Game detection and optimization

### 2. Tunnel Server (`server/`)
- High-performance relay servers
- Load balancing and traffic routing
- Connection management
- Performance monitoring

### 3. Web Dashboard (`dashboard/`)
- Real-time connection statistics
- Server selection interface
- Performance graphs and analytics
- Configuration management

## Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Tunnel Server
```bash
python -m server.main --port 8080 --region us-east
```

### Run Tunnel Client
```bash
python -m client.main --server-host your-server.com --server-port 8080
```

### Launch Web Dashboard
```bash
python -m dashboard.app
```

## Configuration

Edit `config/config.yaml` to customize:
- Server endpoints
- Encryption settings
- Game-specific optimizations
- Monitoring preferences

## Architecture

```
Game Client ←→ Tunnel Client ←→ Tunnel Server ←→ Game Server
                     ↓
                Web Dashboard
```

## Performance

- **Latency Reduction**: Up to 30-60ms improvement for intercontinental connections
- **Packet Loss**: Reduced packet loss through redundant routing
- **Throughput**: Optimized for gaming traffic patterns

## Supported Games

- Counter-Strike 2
- Valorant
- League of Legends
- Dota 2
- Apex Legends
- And many more...

## License

MIT License - See LICENSE file for details
