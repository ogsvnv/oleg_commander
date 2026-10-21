"""CLI for Oleg Commander."""
import asyncio
import sys
from pathlib import Path
from .config import Config
from .server import OlegCommanderServer

def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: oleg-commander [start|status|doctor|config|tools|logs|approvals|approve|reject]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "start":
        # Start the server
        config = Config()
        server = OlegCommanderServer(config)
        try:
            asyncio.run(server.start())
        except KeyboardInterrupt:
            pass
    
    elif command == "status":
        print("Oleg Commander status: Not implemented yet")
        
    elif command == "doctor":
        print("Checking Oleg Commander setup...")
        print("Python version: ", sys.version)
        print("Config file: Present")
        print("Dependencies: Not verified (no pip install)")
        
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()