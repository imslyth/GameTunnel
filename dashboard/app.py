"""
GameTunnel Dashboard - Web interface for monitoring and managing tunnel connections.
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Optional
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import threading

from utils import Config, NetworkUtils, Logger


class DashboardApp:
    """
    Web dashboard for GameTunnel monitoring and management.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Flask app setup
        self.app = Flask(__name__, template_folder='templates')
        self.app.config['SECRET_KEY'] = 'gametunnel-dashboard-secret'
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Dashboard configuration
        self.host = config.get('dashboard.host', '127.0.0.1')
        self.port = config.get('dashboard.port', 5000)
        self.debug = config.get('dashboard.debug', False)
        
        # Data storage
        self.client_stats = {}
        self.server_stats = {}
        self.connection_history = []
        self.active_connections = {}
        
        # Setup routes and socket handlers
        self._setup_routes()
        self._setup_socket_handlers()
        
        # Start background tasks
        self._start_background_tasks()
    
    def _setup_routes(self) -> None:
        """Set up Flask routes."""
        
        @self.app.route('/')
        def index():
            """Main dashboard page."""
            return render_template('dashboard.html')
        
        @self.app.route('/api/stats')
        def get_stats():
            """Get current statistics."""
            return jsonify({
                'client_stats': self.client_stats,
                'server_stats': self.server_stats,
                'active_connections': len(self.active_connections),
                'total_connections': len(self.connection_history)
            })
        
        @self.app.route('/api/servers')
        def get_servers():
            """Get server list with latencies."""
            servers = self.config.get('servers', [])
            return jsonify(servers)
        
        @self.app.route('/api/connections')
        def get_connections():
            """Get active connections."""
            return jsonify(list(self.active_connections.values()))
        
        @self.app.route('/api/history')
        def get_history():
            """Get connection history."""
            # Return last 100 entries
            return jsonify(self.connection_history[-100:])
        
        @self.app.route('/api/config')
        def get_config():
            """Get current configuration."""
            safe_config = {
                'servers': self.config.get('servers', []),
                'games': self.config.get('games', []),
                'tunnel': self.config.get('tunnel', {}),
                'client': {
                    'auto_connect': self.config.get('client.auto_connect', True),
                    'retry_attempts': self.config.get('client.retry_attempts', 3)
                }
            }
            return jsonify(safe_config)
        
        @self.app.route('/static/<path:filename>')
        def static_files(filename):
            """Serve static files."""
            return send_from_directory('dashboard/static', filename)
    
    def _setup_socket_handlers(self) -> None:
        """Set up WebSocket handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection."""
            self.logger.info(f"Dashboard client connected: {request.sid}")
            emit('connected', {'status': 'connected'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection."""
            self.logger.info(f"Dashboard client disconnected: {request.sid}")
        
        @self.socketio.on('ping_server')
        def handle_ping_server(data):
            """Handle server ping request."""
            server_host = data.get('host')
            server_port = data.get('port', 8080)
            
            if server_host:
                # Start ping task
                asyncio.create_task(self._ping_server_for_client(server_host, server_port, request.sid))
        
        @self.socketio.on('get_live_stats')
        def handle_get_live_stats():
            """Handle live stats request."""
            stats = self._get_live_stats()
            emit('live_stats', stats)
    
    def _start_background_tasks(self) -> None:
        """Start background monitoring tasks."""
        def background_worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            tasks = [
                self._monitor_servers(),
                self._update_dashboard_data(),
                self._cleanup_old_data()
            ]
            
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        
        thread = threading.Thread(target=background_worker, daemon=True)
        thread.start()
    
    async def _monitor_servers(self) -> None:
        """Monitor server connectivity and performance."""
        while True:
            try:
                servers = self.config.get('servers', [])
                
                for server in servers:
                    latency, success = await NetworkUtils.ping_host(
                        server['host'], server['port'], timeout=5.0
                    )
                    
                    server_key = f"{server['host']}:{server['port']}"
                    
                    if server_key not in self.server_stats:
                        self.server_stats[server_key] = {
                            'name': server['name'],
                            'host': server['host'],
                            'port': server['port'],
                            'region': server['region'],
                            'location': server['location'],
                            'latency_history': [],
                            'status': 'unknown'
                        }
                    
                    stats = self.server_stats[server_key]
                    stats['latency'] = latency if success else None
                    stats['status'] = 'online' if success else 'offline'
                    stats['last_check'] = time.time()
                    
                    # Keep latency history (last 60 measurements)
                    if success:
                        stats['latency_history'].append({
                            'timestamp': time.time(),
                            'latency': latency
                        })
                        stats['latency_history'] = stats['latency_history'][-60:]
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error monitoring servers: {e}")
                await asyncio.sleep(30)
    
    async def _update_dashboard_data(self) -> None:
        """Update dashboard data and emit to connected clients."""
        while True:
            try:
                # Collect current statistics
                stats = self._get_live_stats()
                
                # Emit to all connected dashboard clients
                self.socketio.emit('live_stats_update', stats)
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Error updating dashboard data: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_old_data(self) -> None:
        """Clean up old data to prevent memory issues."""
        while True:
            try:
                current_time = time.time()
                cutoff_time = current_time - (24 * 3600)  # 24 hours
                
                # Clean connection history
                self.connection_history = [
                    conn for conn in self.connection_history
                    if conn.get('timestamp', 0) > cutoff_time
                ]
                
                # Clean server latency history
                for stats in self.server_stats.values():
                    stats['latency_history'] = [
                        entry for entry in stats['latency_history']
                        if entry['timestamp'] > cutoff_time
                    ]
                
                await asyncio.sleep(3600)  # Cleanup every hour
                
            except Exception as e:
                self.logger.error(f"Error cleaning up data: {e}")
                await asyncio.sleep(3600)
    
    async def _ping_server_for_client(self, host: str, port: int, client_sid: str) -> None:
        """Ping server for specific dashboard client."""
        try:
            latency, success = await NetworkUtils.ping_host(host, port, timeout=10.0)
            
            result = {
                'host': host,
                'port': port,
                'latency': latency if success else None,
                'success': success,
                'timestamp': time.time()
            }
            
            self.socketio.emit('ping_result', result, room=client_sid)
            
        except Exception as e:
            self.logger.error(f"Error pinging server for client: {e}")
            
            result = {
                'host': host,
                'port': port,
                'latency': None,
                'success': False,
                'error': str(e),
                'timestamp': time.time()
            }
            
            self.socketio.emit('ping_result', result, room=client_sid)
    
    def _get_live_stats(self) -> Dict:
        """Get current live statistics."""
        current_time = time.time()
        
        # Calculate summary statistics
        online_servers = sum(1 for stats in self.server_stats.values() 
                           if stats.get('status') == 'online')
        total_servers = len(self.server_stats)
        
        avg_latency = 0
        latency_count = 0
        
        for stats in self.server_stats.values():
            if stats.get('latency') is not None:
                avg_latency += stats['latency']
                latency_count += 1
        
        if latency_count > 0:
            avg_latency /= latency_count
        
        return {
            'timestamp': current_time,
            'servers': {
                'online': online_servers,
                'total': total_servers,
                'avg_latency': avg_latency
            },
            'connections': {
                'active': len(self.active_connections),
                'total': len(self.connection_history)
            },
            'server_details': self.server_stats
        }
    
    def add_connection_event(self, event_type: str, client_info: Dict) -> None:
        """Add connection event to history."""
        event = {
            'timestamp': time.time(),
            'type': event_type,
            'client': client_info
        }
        
        self.connection_history.append(event)
        
        # Keep only last 1000 events
        if len(self.connection_history) > 1000:
            self.connection_history = self.connection_history[-1000:]
    
    def update_client_stats(self, client_id: str, stats: Dict) -> None:
        """Update statistics for a specific client."""
        self.client_stats[client_id] = {
            **stats,
            'last_update': time.time()
        }
    
    def run(self) -> None:
        """Run the dashboard application."""
        self.logger.info(f"Starting dashboard on {self.host}:{self.port}")
        
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=self.debug,
            allow_unsafe_werkzeug=True
        )


def create_dashboard_template() -> str:
    """Create the HTML template for the dashboard."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GameTunnel Dashboard</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .server-card { margin-bottom: 1rem; }
        .latency-good { color: #28a745; }
        .latency-ok { color: #ffc107; }
        .latency-bad { color: #dc3545; }
        .status-online { color: #28a745; }
        .status-offline { color: #dc3545; }
        .stats-card { height: 150px; }
        #latencyChart { max-height: 300px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container-fluid">
            <span class="navbar-brand mb-0 h1">GameTunnel Dashboard</span>
            <span class="navbar-text" id="connection-status">Connecting...</span>
        </div>
    </nav>

    <div class="container-fluid mt-4">
        <!-- Summary Stats -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card stats-card bg-primary text-white">
                    <div class="card-body">
                        <h5 class="card-title">Online Servers</h5>
                        <h2 class="card-text" id="online-servers">-</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card bg-success text-white">
                    <div class="card-body">
                        <h5 class="card-title">Active Connections</h5>
                        <h2 class="card-text" id="active-connections">-</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card bg-info text-white">
                    <div class="card-body">
                        <h5 class="card-title">Average Latency</h5>
                        <h2 class="card-text" id="avg-latency">-</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card bg-warning text-white">
                    <div class="card-body">
                        <h5 class="card-title">Total Connections</h5>
                        <h2 class="card-text" id="total-connections">-</h2>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <!-- Server List -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5>Server Status</h5>
                    </div>
                    <div class="card-body" id="server-list">
                        <div class="text-center">Loading servers...</div>
                    </div>
                </div>
            </div>

            <!-- Latency Chart -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5>Latency History</h5>
                    </div>
                    <div class="card-body">
                        <canvas id="latencyChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <!-- Connection History -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5>Recent Activity</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped" id="activity-table">
                                <thead>
                                    <tr>
                                        <th>Time</th>
                                        <th>Event</th>
                                        <th>Details</th>
                                    </tr>
                                </thead>
                                <tbody id="activity-body">
                                    <tr><td colspan="3" class="text-center">Loading activity...</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Socket.IO connection
        const socket = io();
        
        // Chart setup
        let latencyChart;
        
        socket.on('connect', function() {
            document.getElementById('connection-status').textContent = 'Connected';
            document.getElementById('connection-status').className = 'navbar-text text-success';
        });
        
        socket.on('disconnect', function() {
            document.getElementById('connection-status').textContent = 'Disconnected';
            document.getElementById('connection-status').className = 'navbar-text text-danger';
        });
        
        socket.on('live_stats_update', function(data) {
            updateDashboard(data);
        });
        
        function updateDashboard(data) {
            // Update summary stats
            document.getElementById('online-servers').textContent = 
                `${data.servers.online}/${data.servers.total}`;
            document.getElementById('active-connections').textContent = data.connections.active;
            document.getElementById('avg-latency').textContent = 
                data.servers.avg_latency > 0 ? `${data.servers.avg_latency.toFixed(1)}ms` : '-';
            document.getElementById('total-connections').textContent = data.connections.total;
            
            // Update server list
            updateServerList(data.server_details);
            
            // Update latency chart
            updateLatencyChart(data.server_details);
        }
        
        function updateServerList(servers) {
            const serverList = document.getElementById('server-list');
            let html = '';
            
            for (const [key, server] of Object.entries(servers)) {
                const statusClass = server.status === 'online' ? 'status-online' : 'status-offline';
                const latencyClass = server.latency < 50 ? 'latency-good' : 
                                   server.latency < 100 ? 'latency-ok' : 'latency-bad';
                const latencyText = server.latency ? `${server.latency.toFixed(1)}ms` : 'N/A';
                
                html += `
                    <div class="server-card border rounded p-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <h6 class="mb-1">${server.name}</h6>
                                <small class="text-muted">${server.location} (${server.region})</small>
                            </div>
                            <div class="text-end">
                                <div class="${statusClass} fw-bold">${server.status.toUpperCase()}</div>
                                <div class="${latencyClass}">${latencyText}</div>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            serverList.innerHTML = html || '<div class="text-center">No servers configured</div>';
        }
        
        function updateLatencyChart(servers) {
            const ctx = document.getElementById('latencyChart').getContext('2d');
            
            if (!latencyChart) {
                latencyChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: [],
                        datasets: []
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'Latency (ms)'
                                }
                            }
                        },
                        elements: {
                            point: {
                                radius: 2
                            }
                        }
                    }
                });
            }
            
            // Update chart data
            const datasets = [];
            const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF'];
            let colorIndex = 0;
            
            for (const [key, server] of Object.entries(servers)) {
                if (server.latency_history && server.latency_history.length > 0) {
                    datasets.push({
                        label: server.name,
                        data: server.latency_history.map(entry => ({
                            x: new Date(entry.timestamp * 1000),
                            y: entry.latency
                        })),
                        borderColor: colors[colorIndex % colors.length],
                        backgroundColor: colors[colorIndex % colors.length] + '20',
                        fill: false,
                        tension: 0.1
                    });
                    colorIndex++;
                }
            }
            
            latencyChart.data.datasets = datasets;
            latencyChart.update('none');
        }
        
        // Initialize dashboard
        fetch('/api/stats')
            .then(response => response.json())
            .then(data => {
                // Initial data load
                socket.emit('get_live_stats');
            });
    </script>
</body>
</html>'''


def main():
    """Main entry point for the dashboard."""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="GameTunnel Dashboard")
    parser.add_argument("--config", default="config/config.yaml",
                       help="Configuration file path")
    parser.add_argument("--host", help="Dashboard host address")
    parser.add_argument("--port", type=int, help="Dashboard port")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config(args.config)
    
    # Override config with command line arguments
    if args.host:
        config.config['dashboard']['host'] = args.host
    if args.port:
        config.config['dashboard']['port'] = args.port
    if args.debug:
        config.config['dashboard']['debug'] = True
    
    # Setup logging
    Logger.setup_logging(config)
    logger = logging.getLogger(__name__)
    
    # Create templates directory
    os.makedirs('dashboard/templates', exist_ok=True)
    
    # Create dashboard template - only if it doesn't exist
    template_path = 'dashboard/templates/dashboard.html'
    if not os.path.exists(template_path):
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(create_dashboard_template())
    
    try:
        # Create and run dashboard
        dashboard = DashboardApp(config)
        dashboard.run()
        
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
    except Exception as e:
        logger.error(f"Dashboard error: {e}")


if __name__ == "__main__":
    main()
