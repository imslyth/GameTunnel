"""
GameTunnel Setup Script - Easy installation and configuration.
"""

import os
import sys
import subprocess
import platform
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    
    print(f"✅ Python version: {sys.version}")
    return True


def install_dependencies():
    """Install required Python packages."""
    print("📦 Installing dependencies...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False


def create_directories():
    """Create necessary directories."""
    print("📁 Creating directories...")
    
    directories = [
        "logs",
        "dashboard/templates",
        "dashboard/static",
        "tests"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"   Created: {directory}")
    
    print("✅ Directories created")


def setup_config():
    """Set up configuration file."""
    config_path = Path("config/config.yaml")
    
    if config_path.exists():
        print("✅ Configuration file already exists")
        return True
    
    print("⚙️  Setting up configuration...")
    
    # Configuration is already created, just verify
    if config_path.exists():
        print("✅ Configuration file created")
        return True
    else:
        print("❌ Configuration file not found")
        return False


def check_firewall():
    """Check firewall settings."""
    print("🔥 Checking firewall settings...")
    
    system = platform.system()
    
    if system == "Windows":
        print("   Please ensure GameTunnel is allowed through Windows Firewall")
        print("   Default ports: 8080 (server), 5000 (dashboard)")
    elif system == "Linux":
        print("   Please configure iptables/ufw to allow GameTunnel ports")
        print("   Default ports: 8080 (server), 5000 (dashboard)")
    elif system == "Darwin":  # macOS
        print("   Please configure macOS firewall to allow GameTunnel")
        print("   Default ports: 8080 (server), 5000 (dashboard)")
    
    print("✅ Firewall check complete (manual configuration may be required)")


def run_quick_test():
    """Run a quick test to verify installation."""
    print("🧪 Running quick test...")
    
    try:
        # Test imports
        from utils import Config, NetworkUtils
        from client.main import TunnelClient
        from server.main import TunnelServer
        from dashboard.app import DashboardApp
        
        # Test configuration loading
        config = Config("config/config.yaml")
        
        print("✅ All modules imported successfully")
        print("✅ Configuration loaded successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def print_usage_instructions():
    """Print usage instructions."""
    print("\n" + "="*60)
    print("🎮 GameTunnel Setup Complete!")
    print("="*60)
    print()
    print("Usage Examples:")
    print()
    print("1. Start a tunnel server:")
    print("   python main.py server --host 0.0.0.0 --port 8080 --region us-east")
    print()
    print("2. Connect tunnel client:")
    print("   python main.py client --server-host your-server.com --server-port 8080")
    print()
    print("3. Launch web dashboard:")
    print("   python main.py dashboard --host 127.0.0.1 --port 5000")
    print()
    print("Configuration:")
    print("   Edit config/config.yaml to customize settings")
    print()
    print("Logs:")
    print("   Check logs/gametunnel.log for application logs")
    print()
    print("For more information, see README.md")
    print("="*60)


def main():
    """Main setup function."""
    print("🚀 GameTunnel Setup")
    print("Setting up your network optimization environment...")
    print()
    
    # Run setup steps
    steps = [
        ("Checking Python version", check_python_version),
        ("Installing dependencies", install_dependencies),
        ("Creating directories", create_directories),
        ("Setting up configuration", setup_config),
        ("Checking firewall", check_firewall),
        ("Running tests", run_quick_test)
    ]
    
    failed_steps = []
    
    for step_name, step_func in steps:
        print(f"\n{step_name}...")
        if not step_func():
            failed_steps.append(step_name)
    
    print("\n" + "="*60)
    
    if failed_steps:
        print("❌ Setup completed with errors:")
        for step in failed_steps:
            print(f"   - {step}")
        print("\nPlease resolve the issues above before running GameTunnel.")
    else:
        print("✅ Setup completed successfully!")
        print_usage_instructions()


if __name__ == "__main__":
    main()
