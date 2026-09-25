"""database MCP tool - Query PostgreSQL application database.

Provides read access to the megacorpai application database.
Supports queries against customer and project data.
"""

# Database connection is configured via environment variables:
# DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# See /etc/mcp/db-config.json for connection details

def query(sql):
    """Execute a SQL query against the application database."""
    # Implementation handled by MCP server framework
    pass
