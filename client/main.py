"""
GameTunnel Client - Routes game traffic through optimized tunnel servers.
"""

import asyncio
import logging
import socket
import time
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
import struct

from utils import Config, NetworkUtils, ServerInfo, ConnectionStats, GameDetector, Logger


class TunnelClient:
    """
    Main tunnel client that routes game traffic through optimized servers.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.game_detector = GameDetector(config)
        
        # Connection state
        self.connected = False
        self.current_server: Optional[ServerInfo] = None
        self.tunnel_socket: Optional[socket.socket] = None
        self.stats = ConnectionStats()
        
        # Server management
        self.servers: List[ServerInfo] = []
        self.server_latencies: Dict[str, float] = {}
        
        # Traffic routing
        self.local_socket: Optional[socket.socket] = None
        self.running = False
        
    async def initialize(self) -> None:
        """Initialize the tunnel client."""
        self.logger.info("Initializing GameTunnel Client...")
        
        # Load server list
        await self._load_servers()
        
        # Test server connectivity
        await self._test_all_servers()
        
        # Select best server
        await self._select_best_server()
        
        self.logger.info(f"Client initialized with {len(self.servers)} servers")
    
    async def start(self) -> None:
        """Start the tunnel client."""
        if not self.current_server:
            raise RuntimeError("No available servers")
        
        self.logger.info(f"Starting tunnel client, connecting to {self.current_server.name}")
        self.running = True
        
        # Create local proxy socket
        await self._create_local_proxy()
        
        # Connect to tunnel server
        await self._connect_to_server()
        
        # Start traffic handling
        await self._start_traffic_handlers()
        
        self.logger.info("Tunnel client started successfully")
    
    async def stop(self) -> None:
        """Stop the tunnel client."""
        self.logger.info("Stopping tunnel client...")
        self.running = False
        
        if self.tunnel_socket:
            self.tunnel_socket.close()
        
        if self.local_socket:
            self.local_socket.close()
        
        self.connected = False
        self.logger.info("Tunnel client stopped")
    
    async def _load_servers(self) -> None:
        """Load server list from configuration."""
        server_configs = self.config.get('servers', [])
        
        for server_config in server_configs:
            server = ServerInfo(
                name=server_config['name'],
                host=server_config['host'],
                port=server_config['port'],
                region=server_config['region'],
                location=server_config['location']
            )
            self.servers.append(server)
    
    async def _test_all_servers(self) -> None:
        """Test connectivity and latency to all servers."""
        self.logger.info("Testing server connectivity...")
        
        tasks = []
        for server in self.servers:
            task = asyncio.create_task(self._test_server(server))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _test_server(self, server: ServerInfo) -> None:
        """Test connectivity to a specific server."""
        try:
            # Perform multiple pings for accuracy
            latencies = []
            
            for _ in range(3):
                latency, success = await NetworkUtils.ping_host(
                    server.host, server.port, timeout=5.0
                )
                
                if success:
                    latencies.append(latency)
                    await asyncio.sleep(0.1)
            
            if latencies:
                server.latency = sum(latencies) / len(latencies)
                server.last_ping = time.time()
                self.server_latencies[server.name] = server.latency
                
                self.logger.info(f"Server {server.name}: {server.latency:.1f}ms")
            else:
                server.latency = float('inf')
                self.logger.warning(f"Server {server.name}: Unreachable")
                
        except Exception as e:
            self.logger.error(f"Error testing server {server.name}: {e}")
            server.latency = float('inf')
    
    async def _select_best_server(self) -> None:
        """Select the server with the lowest latency."""
        available_servers = [s for s in self.servers if s.latency < float('inf')]
        
        if not available_servers:
            raise RuntimeError("No available servers found")
        
        # Sort by latency and select the best one
        available_servers.sort(key=lambda s: s.latency)
        self.current_server = available_servers[0]
        
        self.logger.info(f"Selected server: {self.current_server.name} "
                        f"({self.current_server.latency:.1f}ms)")
    
    async def _create_local_proxy(self) -> None:
        """Create local proxy socket for intercepting game traffic."""
        self.local_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to a local port
        local_port = self.config.get('client.local_port', 0)  # 0 = auto-assign
        self.local_socket.bind(('127.0.0.1', local_port))
        
        actual_port = self.local_socket.getsockname()[1]
        self.logger.info(f"Local proxy listening on port {actual_port}")
    
    async def _connect_to_server(self) -> None:
        """Connect to the selected tunnel server."""
        try:
            self.tunnel_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tunnel_socket.settimeout(10.0)
            
            await asyncio.get_event_loop().run_in_executor(
                None, 
                self.tunnel_socket.connect,
                (self.current_server.host, self.current_server.port)
            )
            
            self.tunnel_socket.settimeout(None)
            self.connected = True
            self.stats.connection_time = time.time()
            
            self.logger.info(f"Connected to {self.current_server.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to server: {e}")
            raise
    
    async def _start_traffic_handlers(self) -> None:
        """Start traffic handling tasks."""
        tasks = [
            asyncio.create_task(self._handle_local_traffic()),
            asyncio.create_task(self._handle_tunnel_traffic()),
            asyncio.create_task(self._monitor_connection())
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _handle_local_traffic(self) -> None:
        """Handle traffic from local games to tunnel."""
        self.logger.info("Starting local traffic handler")
        
        while self.running and self.connected:
            try:
                # Receive data from local games
                data, addr = await asyncio.get_event_loop().run_in_executor(
                    None, self.local_socket.recvfrom, 4096
                )
                
                if data and self.tunnel_socket:
                    # Forward to tunnel server
                    packet = self._create_tunnel_packet(data, addr)
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.tunnel_socket.send, packet
                    )
                    
                    self.stats.bytes_sent += len(data)
                    self.stats.packets_sent += 1
                    
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in local traffic handler: {e}")
                break
    
    async def _handle_tunnel_traffic(self) -> None:
        """Handle traffic from tunnel back to local games."""
        self.logger.info("Starting tunnel traffic handler")
        
        while self.running and self.connected and self.tunnel_socket:
            try:
                # Receive data from tunnel server
                data = await asyncio.get_event_loop().run_in_executor(
                    None, self.tunnel_socket.recv, 4096
                )
                
                if not data:
                    break
                
                # Parse tunnel packet and forward to local game
                game_data, target_addr = self._parse_tunnel_packet(data)
                
                if game_data and target_addr:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.local_socket.sendto, game_data, target_addr
                    )
                    
                    self.stats.bytes_received += len(game_data)
                    self.stats.packets_received += 1
                    
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in tunnel traffic handler: {e}")
                break
    
    async def _monitor_connection(self) -> None:
        """Monitor connection health and performance."""
        while self.running and self.connected:
            try:
                # Send heartbeat
                if self.tunnel_socket:
                    heartbeat = b"HEARTBEAT"
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.tunnel_socket.send, heartbeat
                    )
                
                # Update latency statistics
                if self.current_server:
                    latency, success = await NetworkUtils.ping_host(
                        self.current_server.host, self.current_server.port
                    )
                    if success:
                        self.stats.avg_latency = latency
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Connection monitoring error: {e}")
                break
    
    def _create_tunnel_packet(self, data: bytes, addr: Tuple[str, int]) -> bytes:
        """Create a tunnel packet with routing information."""
        # Simple packet format: [addr_len][addr][data_len][data]
        addr_bytes = f"{addr[0]}:{addr[1]}".encode('utf-8')
        addr_len = len(addr_bytes)
        data_len = len(data)
        
        packet = struct.pack(f"!I{addr_len}sI{data_len}s", 
                           addr_len, addr_bytes, data_len, data)
        return packet
    
    def _parse_tunnel_packet(self, packet: bytes) -> Tuple[Optional[bytes], Optional[Tuple[str, int]]]:
        """Parse tunnel packet to extract game data and target address."""
        try:
            # Parse packet format: [addr_len][addr][data_len][data]
            offset = 0
            
            addr_len = struct.unpack("!I", packet[offset:offset+4])[0]
            offset += 4
            
            addr_bytes = packet[offset:offset+addr_len]
            addr_str = addr_bytes.decode('utf-8')
            host, port = addr_str.split(':')
            addr = (host, int(port))
            offset += addr_len
            
            data_len = struct.unpack("!I", packet[offset:offset+4])[0]
            offset += 4
            
            data = packet[offset:offset+data_len]
            
            return data, addr
            
        except Exception as e:
            self.logger.error(f"Error parsing tunnel packet: {e}")
            return None, None
    
    def get_stats(self) -> ConnectionStats:
        """Get current connection statistics."""
        return self.stats
    
    def get_current_server(self) -> Optional[ServerInfo]:
        """Get currently connected server."""
        return self.current_server
    
    async def switch_server(self, server_name: str) -> bool:
        """Switch to a different server."""
        target_server = next((s for s in self.servers if s.name == server_name), None)
        
        if not target_server:
            self.logger.error(f"Server {server_name} not found")
            return False
        
        self.logger.info(f"Switching to server {server_name}")
        
        # Disconnect from current server
        if self.tunnel_socket:
            self.tunnel_socket.close()
            self.connected = False
        
        # Update current server and reconnect
        self.current_server = target_server
        
        try:
            await self._connect_to_server()
            return True
        except Exception as e:
            self.logger.error(f"Failed to switch server: {e}")
            return False


async def main():
    """Main entry point for the tunnel client."""
    import argparse
    
    parser = argparse.ArgumentParser(description="GameTunnel Client")
    parser.add_argument("--config", default="config/config.yaml", 
                       help="Configuration file path")
    parser.add_argument("--server", help="Specific server to connect to")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Setup logging
    if args.verbose:
        config.config['logging']['level'] = 'DEBUG'
    
    Logger.setup_logging(config)
    logger = logging.getLogger(__name__)
    
    try:
        # Create and start tunnel client
        client = TunnelClient(config)
        await client.initialize()
        
        # Force specific server if requested
        if args.server:
            target_server = next((s for s in client.servers if s.name == args.server), None)
            if target_server:
                client.current_server = target_server
                logger.info(f"Forced server selection: {args.server}")
            else:
                logger.error(f"Server {args.server} not found")
                return
        
        await client.start()
        
        # Keep running until interrupted
        try:
            while client.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        
    except Exception as e:
        logger.error(f"Client error: {e}")
    
    finally:
        if 'client' in locals():
            await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
