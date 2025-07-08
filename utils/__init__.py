"""
GameTunnel - Network optimization utilities and shared components.
"""

import asyncio
import logging
import time
import socket
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
import yaml
import os

# Optional import for game detection
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@dataclass
class ServerInfo:
    """Information about a tunnel server."""
    name: str
    host: str
    port: int
    region: str
    location: str
    latency: float = 0.0
    packet_loss: float = 0.0
    last_ping: float = 0.0


@dataclass
class ConnectionStats:
    """Connection statistics."""
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    connection_time: float = 0.0
    avg_latency: float = 0.0
    packet_loss: float = 0.0


class Config:
    """Configuration manager for GameTunnel."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logging.warning(f"Config file {self.config_path} not found, using defaults")
            self.config = self._get_default_config()
        except yaml.YAMLError as e:
            logging.error(f"Error parsing config file: {e}")
            self.config = self._get_default_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'server': {
                'host': '0.0.0.0',
                'port': 8080,
                'max_connections': 1000,
                'buffer_size': 65536
            },
            'client': {
                'auto_connect': True,
                'retry_attempts': 3,
                'retry_delay': 5,
                'heartbeat_interval': 30
            },
            'tunnel': {
                'encryption': True,
                'compression': True,
                'mtu': 1400,
                'keepalive': 60
            },
            'logging': {
                'level': 'INFO',
                'file': 'logs/gametunnel.log'
            }
        }


class NetworkUtils:
    """Network utility functions."""
    
    @staticmethod
    async def ping_host(host: str, port: int, timeout: float = 5.0) -> Tuple[float, bool]:
        """
        Ping a host and return latency and success status.
        
        Args:
            host: Target hostname or IP
            port: Target port
            timeout: Connection timeout in seconds
            
        Returns:
            Tuple of (latency_ms, success)
        """
        start_time = time.time()
        
        try:
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=timeout)
            
            latency = (time.time() - start_time) * 1000
            
            writer.close()
            await writer.wait_closed()
            
            return latency, True
            
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return 0.0, False
    
    @staticmethod
    def get_local_ip() -> str:
        """Get local IP address."""
        try:
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    @staticmethod
    def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        """Check if a port is already in use."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return False
        except OSError:
            return True


class Logger:
    """Logging setup and utilities."""
    
    @staticmethod
    def setup_logging(config: Config) -> None:
        """Set up logging configuration."""
        log_level = config.get('logging.level', 'INFO')
        log_file = config.get('logging.file', 'logs/gametunnel.log')
        
        # Create logs directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )


class GameDetector:
    """Detect running games and their network requirements."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.games = config.get('games', [])
    
    def detect_running_games(self) -> list:
        """Detect currently running games."""
        if not PSUTIL_AVAILABLE:
            self.logger.warning("psutil not available, cannot detect running games")
            return []
        
        detected_games = []
        running_processes = [p.info for p in psutil.process_iter(['pid', 'name', 'exe'])]
        
        for game in self.games:
            game_exe = game.get('executable', '').lower()
            
            for process in running_processes:
                if process['name'] and game_exe in process['name'].lower():
                    detected_games.append({
                        'name': game['name'],
                        'process': process,
                        'ports': game.get('ports', []),
                        'protocol': game.get('protocol', 'udp'),
                        'optimization': game.get('optimization', 'default')
                    })
                    break
        
        return detected_games


def format_bytes(bytes_value: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def format_latency(latency_ms: float) -> str:
    """Format latency to human readable string."""
    if latency_ms < 1:
        return f"{latency_ms * 1000:.0f}μs"
    elif latency_ms < 1000:
        return f"{latency_ms:.1f}ms"
    else:
        return f"{latency_ms / 1000:.2f}s"
