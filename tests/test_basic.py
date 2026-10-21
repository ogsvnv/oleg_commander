"""Basic tests for Oleg Commander."""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

def test_imports():
    """Test that all modules can be imported."""
    from oleg_commander import config
    from oleg_commander import security
    from oleg_commander import server
    from oleg_commander.tools import filesystem, terminal, ssh, git
    from oleg_commander.services import path_service, approval_service
    
    assert config is not None
    assert security is not None
    assert server is not None
    assert filesystem is not None
    assert terminal is not None
    assert ssh is not None
    assert git is not None
    assert path_service is not None
    assert approval_service is not None
    
def test_tool_creation():
    """Test that tools can be created."""
    from oleg_commander.config import Config
    from oleg_commander.security import SecurityManager
    from oleg_commander.tools.filesystem import FilesystemTool
    
    config = Config()
    security_manager = SecurityManager(config)
    
    # Test creating filesystem tool
    fs_tool = FilesystemTool(security_manager)
    assert fs_tool is not None

if __name__ == "__main__":
    test_imports()
    test_tool_creation()
    print("All basic tests passed!")