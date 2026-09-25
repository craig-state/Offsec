"""filesystem MCP tool - Access shared files.

Provides read access to files in /data/shared/.
Used for accessing shared documents and reports.
"""

ALLOWED_PATHS = ["/data/shared/"]

def read_file(path):
    """Read a file from the allowed paths."""
    pass

def list_files(path="/data/shared/"):
    """List files in a directory."""
    pass
