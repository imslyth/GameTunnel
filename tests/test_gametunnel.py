"""
GameTunnel Tests - Unit tests for core functionality.
"""

import unittest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import Config, NetworkUtils, ServerInfo, ConnectionStats
from client.main import TunnelClient
from server.main import TunnelServer


class TestConfig(unittest.TestCase):
    """Test configuration management."""
    
    def test_config_loading(self):
        """Test configuration file loading."""
        config = Config("config/config.yaml")
        
        # Test default values
        self.assertIsInstance(config.get('server.port', 8080), int)
        self.assertIsInstance(config.get('client.auto_connect', True), bool)
    
    def test_config_get_nested(self):
        """Test nested configuration access."""
        config = Config()
        config.config = {
            'server': {'host': '0.0.0.0', 'port': 8080},
            'client': {'auto_connect': True}
        }
        
        self.assertEqual(config.get('server.host'), '0.0.0.0')
        self.assertEqual(config.get('server.port'), 8080)
        self.assertEqual(config.get('client.auto_connect'), True)
        self.assertIsNone(config.get('nonexistent.key'))


class TestNetworkUtils(unittest.TestCase):
    """Test network utility functions."""
    
    def test_get_local_ip(self):
        """Test local IP address detection."""
        ip = NetworkUtils.get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip) > 0)
    
    def test_is_port_in_use(self):
        """Test port availability checking."""
        # Test a likely unused high port
        self.assertFalse(NetworkUtils.is_port_in_use(65432))
    
    @patch('asyncio.open_connection')
    async def test_ping_host_success(self, mock_open_connection):
        """Test successful host ping."""
        # Mock successful connection
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)
        
        latency, success = await NetworkUtils.ping_host("example.com", 80, timeout=5.0)
        
        self.assertTrue(success)
        self.assertGreater(latency, 0)
        mock_writer.close.assert_called_once()
    
    @patch('asyncio.open_connection')
    async def test_ping_host_failure(self, mock_open_connection):
        """Test failed host ping."""
        # Mock connection failure
        mock_open_connection.side_effect = ConnectionRefusedError("Connection refused")
        
        latency, success = await NetworkUtils.ping_host("nonexistent.com", 80, timeout=5.0)
        
        self.assertFalse(success)
        self.assertEqual(latency, 0.0)


class TestServerInfo(unittest.TestCase):
    """Test ServerInfo data class."""
    
    def test_server_info_creation(self):
        """Test ServerInfo creation."""
        server = ServerInfo(
            name="Test Server",
            host="test.example.com",
            port=8080,
            region="us-east",
            location="New York"
        )
        
        self.assertEqual(server.name, "Test Server")
        self.assertEqual(server.host, "test.example.com")
        self.assertEqual(server.port, 8080)
        self.assertEqual(server.region, "us-east")
        self.assertEqual(server.location, "New York")
        self.assertEqual(server.latency, 0.0)


class TestConnectionStats(unittest.TestCase):
    """Test ConnectionStats data class."""
    
    def test_connection_stats_creation(self):
        """Test ConnectionStats creation."""
        stats = ConnectionStats()
        
        self.assertEqual(stats.bytes_sent, 0)
        self.assertEqual(stats.bytes_received, 0)
        self.assertEqual(stats.packets_sent, 0)
        self.assertEqual(stats.packets_received, 0)
        self.assertEqual(stats.connection_time, 0.0)
        self.assertEqual(stats.avg_latency, 0.0)
        self.assertEqual(stats.packet_loss, 0.0)


class TestTunnelClient(unittest.TestCase):
    """Test tunnel client functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.config = {
            'servers': [
                {
                    'name': 'Test Server',
                    'host': 'test.example.com',
                    'port': 8080,
                    'region': 'test',
                    'location': 'Test Location'
                }
            ],
            'client': {
                'auto_connect': True,
                'retry_attempts': 3,
                'retry_delay': 5,
                'heartbeat_interval': 30
            }
        }
    
    def test_client_creation(self):
        """Test tunnel client creation."""
        client = TunnelClient(self.config)
        
        self.assertIsInstance(client, TunnelClient)
        self.assertEqual(client.config, self.config)
        self.assertFalse(client.connected)
        self.assertIsNone(client.current_server)
    
    async def test_client_load_servers(self):
        """Test loading servers from configuration."""
        client = TunnelClient(self.config)
        await client._load_servers()
        
        self.assertEqual(len(client.servers), 1)
        self.assertEqual(client.servers[0].name, 'Test Server')
        self.assertEqual(client.servers[0].host, 'test.example.com')
    
    @patch.object(TunnelClient, '_test_server')
    async def test_client_test_all_servers(self, mock_test_server):
        """Test testing all servers."""
        client = TunnelClient(self.config)
        await client._load_servers()
        
        mock_test_server.return_value = None
        await client._test_all_servers()
        
        mock_test_server.assert_called_once()


class TestTunnelServer(unittest.TestCase):
    """Test tunnel server functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.config = {
            'server': {
                'host': '127.0.0.1',
                'port': 8080,
                'max_connections': 1000,
                'buffer_size': 65536
            }
        }
    
    def test_server_creation(self):
        """Test tunnel server creation."""
        server = TunnelServer(self.config)
        
        self.assertIsInstance(server, TunnelServer)
        self.assertEqual(server.config, self.config)
        self.assertEqual(server.host, '127.0.0.1')
        self.assertEqual(server.port, 8080)
        self.assertFalse(server.running)
    
    def test_server_get_stats(self):
        """Test server statistics."""
        server = TunnelServer(self.config)
        server.start_time = time.time()
        
        stats = server.get_server_stats()
        
        self.assertIsInstance(stats, dict)
        self.assertIn('uptime', stats)
        self.assertIn('active_clients', stats)
        self.assertIn('total_connections', stats)
        self.assertEqual(stats['active_clients'], 0)


class TestPacketHandling(unittest.TestCase):
    """Test packet creation and parsing."""
    
    def test_tunnel_packet_creation_and_parsing(self):
        """Test tunnel packet creation and parsing."""
        client = TunnelClient(Config())
        
        # Test data
        test_data = b"Hello, Game Server!"
        test_addr = ("192.168.1.100", 27015)
        
        # Create packet
        packet = client._create_tunnel_packet(test_data, test_addr)
        
        # Parse packet
        parsed_data, parsed_addr = client._parse_tunnel_packet(packet)
        
        # Verify
        self.assertEqual(parsed_data, test_data)
        self.assertEqual(parsed_addr, test_addr)
    
    def test_invalid_packet_parsing(self):
        """Test parsing of invalid packets."""
        client = TunnelClient(Config())
        
        # Test with invalid packet
        invalid_packet = b"invalid packet data"
        
        parsed_data, parsed_addr = client._parse_tunnel_packet(invalid_packet)
        
        self.assertIsNone(parsed_data)
        self.assertIsNone(parsed_addr)


def run_async_test(coro):
    """Helper function to run async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)
