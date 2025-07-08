import asyncio
import logging
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import Config, Logger
from client.main import TunnelClient
from server.main import TunnelServer
from dashboard.app import DashboardApp


def main():
    parser = argparse.ArgumentParser(description="GameTunnel - Network optimization for gaming")
    parser.add_argument("mode", choices=["client", "server", "dashboard"],
                       help="Application mode to run")
    parser.add_argument("--config", default="config/config.yaml",
                       help="Configuration file path")
    parser.add_argument("--host", help="Host address")
    parser.add_argument("--port", type=int, help="Port number")
    parser.add_argument("--server-host", help="Tunnel server host (client mode)")
    parser.add_argument("--server-port", type=int, help="Tunnel server port (client mode)")
    parser.add_argument("--region", help="Server region (server mode)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug mode")
    
    args = parser.parse_args()
    
    config = Config(args.config)
    
    if args.verbose:
        config.config['logging']['level'] = 'DEBUG'
    
    Logger.setup_logging(config)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting GameTunnel in {args.mode} mode")
    
    try:
        if args.mode == "client":
            run_client(config, args)
        elif args.mode == "server":
            run_server(config, args)
        elif args.mode == "dashboard":
            run_dashboard(config, args)
    
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)


def run_client(config: Config, args) -> None:
    logger = logging.getLogger(__name__)
    
    if args.server_host:
        servers = config.get('servers', [])
        server_port = args.server_port or 8080
        
        existing_server = None
        for server in servers:
            if server['host'] == args.server_host and server['port'] == server_port:
                existing_server = server
                break
        
        if not existing_server:
            temp_server = {
                'name': f"Custom-{args.server_host}",
                'host': args.server_host,
                'port': server_port,
                'region': 'custom',
                'location': 'Custom'
            }
            servers.append(temp_server)
            config.config['servers'] = servers
    
    async def run_client_async():
        client = TunnelClient(config)
        await client.initialize()
        
        if args.server_host:
            target_server = next((s for s in client.servers 
                                if s.host == args.server_host), None)
            if target_server:
                client.current_server = target_server
                logger.info(f"Using specified server: {args.server_host}")
        
        await client.start()
        
        try:
            while client.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await client.stop()
    
    asyncio.run(run_client_async())


def run_server(config: Config, args) -> None:
    if args.host:
        config.config['server']['host'] = args.host
    if args.port:
        config.config['server']['port'] = args.port
    
    async def run_server_async():
        server = TunnelServer(config)
        await server.start()
    
    asyncio.run(run_server_async())


def run_dashboard(config: Config, args) -> None:
    if args.host:
        config.config['dashboard']['host'] = args.host
    if args.port:
        config.config['dashboard']['port'] = args.port
    if args.debug:
        config.config['dashboard']['debug'] = True
    
    dashboard = DashboardApp(config)
    dashboard.run()


if __name__ == "__main__":
    main()
