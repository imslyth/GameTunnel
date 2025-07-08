import asyncio
import logging
import socket
import time
import struct
from typing import Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
import weakref

from utils import Config, NetworkUtils, ConnectionStats, Logger


@dataclass
class ClientConnection:
    client_id: str
    socket: Optional[socket.socket]
    address: Tuple[str, int]
    connected_time: float
    last_activity: float
    stats: ConnectionStats = field(default_factory=ConnectionStats)
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None


class TunnelServer:
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.host = config.get('server.host', '0.0.0.0')
        self.port = config.get('server.port', 8080)
        self.max_connections = config.get('server.max_connections', 1000)
        self.buffer_size = config.get('server.buffer_size', 65536)
        
        self.clients: Dict[str, ClientConnection] = {}
        self.server_socket: Optional[socket.socket] = None
        self.server: Optional[asyncio.Server] = None
        self.running = False
        
        self.total_bytes_relayed = 0
        self.total_connections = 0
        self.start_time = 0.0
        
        self.game_server_pools: Dict[str, Set[socket.socket]] = {}
    
    async def start(self) -> None:
        self.logger.info(f"Starting tunnel server on {self.host}:{self.port}")
        
        try:
            self.running = True
            self.start_time = time.time()
            
            self.server = await asyncio.start_server(
                self._handle_client_connection,
                self.host,
                self.port,
                limit=self.buffer_size
            )
            
            self.logger.info(f"Tunnel server started successfully")
            
            tasks = [
                asyncio.create_task(self._cleanup_inactive_clients()),
                asyncio.create_task(self._log_statistics()),
                asyncio.create_task(self.server.serve_forever())
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            raise
    
    async def stop(self) -> None:
        self.logger.info("Stopping tunnel server...")
        self.running = False
        
        for client in list(self.clients.values()):
            try:
                client.socket.close()
            except Exception:
                pass
        
        self.clients.clear()
        
        if self.server_socket:
            self.server_socket.close()
        
        for pool in self.game_server_pools.values():
            for sock in pool:
                try:
                    sock.close()
                except Exception:
                    pass
        
        self.game_server_pools.clear()
        self.logger.info("Tunnel server stopped")
                    
    async def _handle_client_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client_address = writer.get_extra_info('peername')
        
        if len(self.clients) >= self.max_connections:
            self.logger.warning(f"Max connections reached, rejecting {client_address}")
            writer.close()
            await writer.wait_closed()
            return
        
        client_id = f"{client_address[0]}:{client_address[1]}:{time.time()}"
        client_conn = ClientConnection(
            client_id=client_id,
            socket=None,
            address=client_address,
            connected_time=time.time(),
            last_activity=time.time()
        )
        
        client_conn.reader = reader
        client_conn.writer = writer
        
        self.clients[client_id] = client_conn
        self.total_connections += 1
        
        self.logger.info(f"New client connected: {client_address} (ID: {client_id})")
        
        await self._handle_client(client_conn)
    
    async def _handle_client(self, client: ClientConnection) -> None:
        client_id = client.client_id
        self.logger.info(f"Started handling client {client_id}")
        
        try:
            while self.running and client_id in self.clients:
                data = await client.reader.read(self.buffer_size)
                
                if not data:
                    break
                
                client.last_activity = time.time()
                client.stats.bytes_received += len(data)
                client.stats.packets_received += 1
                
                if data == b"HEARTBEAT":
                    await self._handle_heartbeat(client)
                else:
                    await self._handle_tunnel_packet(client, data)
                
        except Exception as e:
            if self.running:
                self.logger.error(f"Error handling client {client_id}: {e}")
        
        finally:
            await self._disconnect_client(client_id)
    
    async def _handle_heartbeat(self, client: ClientConnection) -> None:
        try:
            client.writer.write(b"HEARTBEAT_ACK")
            await client.writer.drain()
            client.stats.bytes_sent += len(b"HEARTBEAT_ACK")
            client.stats.packets_sent += 1
        except Exception as e:
            self.logger.error(f"Error sending heartbeat ack to {client.client_id}: {e}")
    
    async def _handle_tunnel_packet(self, client: ClientConnection, packet: bytes) -> None:
        try:
            game_data, target_addr = self._parse_tunnel_packet(packet)
            
            if not game_data or not target_addr:
                return
            
            response_data = await self._forward_to_game_server(game_data, target_addr)
            
            if response_data:
                response_packet = self._create_tunnel_packet(response_data, target_addr)
                client.writer.write(response_packet)
                await client.writer.drain()
                
                client.stats.bytes_sent += len(response_packet)
                client.stats.packets_sent += 1
                
                self.total_bytes_relayed += len(game_data) + len(response_data)
            
        except Exception as e:
            self.logger.error(f"Error handling tunnel packet from {client.client_id}: {e}")
    
    async def _forward_to_game_server(self, data: bytes, target_addr: Tuple[str, int]) -> Optional[bytes]:
        try:
            game_socket = await self._get_game_server_connection(target_addr)
            
            if not game_socket:
                return None
            
            await asyncio.get_event_loop().run_in_executor(
                None, game_socket.send, data
            )
            
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, game_socket.recv, self.buffer_size
                ),
                timeout=5.0
            )
            
            return response
            
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout forwarding to {target_addr}")
            return None
        except Exception as e:
            self.logger.error(f"Error forwarding to game server {target_addr}: {e}")
            return None
    
    async def _get_game_server_connection(self, target_addr: Tuple[str, int]) -> Optional[socket.socket]:
        server_key = f"{target_addr[0]}:{target_addr[1]}"
        
        if server_key not in self.game_server_pools:
            self.game_server_pools[server_key] = set()
        
        pool = self.game_server_pools[server_key]
        
        for sock in list(pool):
            try:
                sock.getpeername()
                return sock
            except OSError:
                pool.discard(sock)
                try:
                    sock.close()
                except Exception:
                    pass
        
        try:
            game_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            game_socket.settimeout(5.0)
            
            await asyncio.get_event_loop().run_in_executor(
                None, game_socket.connect, target_addr
            )
            
            game_socket.settimeout(None)
            pool.add(game_socket)
            
            self.logger.debug(f"Created new connection to {target_addr}")
            return game_socket
            
        except Exception as e:
            self.logger.error(f"Failed to connect to game server {target_addr}: {e}")
            return None
    
    def _parse_tunnel_packet(self, packet: bytes) -> Tuple[Optional[bytes], Optional[Tuple[str, int]]]:
        try:
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
    
    def _create_tunnel_packet(self, data: bytes, addr: Tuple[str, int]) -> bytes:
        addr_bytes = f"{addr[0]}:{addr[1]}".encode('utf-8')
        addr_len = len(addr_bytes)
        data_len = len(data)
        
        packet = struct.pack(f"!I{addr_len}sI{data_len}s", 
                           addr_len, addr_bytes, data_len, data)
        return packet
    
    async def _disconnect_client(self, client_id: str) -> None:
        if client_id in self.clients:
            client = self.clients[client_id]
            
            try:
                client.socket.close()
            except Exception:
                pass
            
            del self.clients[client_id]
            
            connection_time = time.time() - client.connected_time
            self.logger.info(f"Client {client_id} disconnected after {connection_time:.1f}s")
    
    async def _cleanup_inactive_clients(self) -> None:
        while self.running:
            try:
                current_time = time.time()
                timeout = 300
                
                inactive_clients = []
                for client_id, client in self.clients.items():
                    if current_time - client.last_activity > timeout:
                        inactive_clients.append(client_id)
                
                for client_id in inactive_clients:
                    self.logger.info(f"Cleaning up inactive client {client_id}")
                    await self._disconnect_client(client_id)
                
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in client cleanup: {e}")
                await asyncio.sleep(60)
    
    async def _log_statistics(self) -> None:
        """Periodically log server statistics."""
        while self.running:
            try:
                uptime = time.time() - self.start_time
                active_clients = len(self.clients)
                
                self.logger.info(
                    f"Server stats - Uptime: {uptime:.0f}s, "
                    f"Active clients: {active_clients}, "
                    f"Total connections: {self.total_connections}, "
                    f"Data relayed: {self._format_bytes(self.total_bytes_relayed)}"
                )
                
                await asyncio.sleep(300)  # Log every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Error logging statistics: {e}")
                await asyncio.sleep(300)
    
    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"
    
    def get_server_stats(self) -> Dict:
        """Get current server statistics."""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            'uptime': uptime,
            'active_clients': len(self.clients),
            'total_connections': self.total_connections,
            'total_bytes_relayed': self.total_bytes_relayed,
            'game_server_pools': len(self.game_server_pools),
            'host': self.host,
            'port': self.port
        }


async def main():
    """Main entry point for the tunnel server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="GameTunnel Server")
    parser.add_argument("--config", default="config/config.yaml",
                       help="Configuration file path")
    parser.add_argument("--host", help="Server host address")
    parser.add_argument("--port", type=int, help="Server port")
    parser.add_argument("--region", help="Server region identifier")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Override config with command line arguments
    if args.host:
        config.config['server']['host'] = args.host
    if args.port:
        config.config['server']['port'] = args.port
    
    # Setup logging
    if args.verbose:
        config.config['logging']['level'] = 'DEBUG'
    
    Logger.setup_logging(config)
    logger = logging.getLogger(__name__)
    
    try:
        # Create and start tunnel server
        server = TunnelServer(config)
        
        if args.region:
            logger.info(f"Server region: {args.region}")
        
        await server.start()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        if 'server' in locals():
            await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
