# MCP Tools

MCP server source code for the MegaCorpAI AI assistant platform.

## Servers

| Server | Description | Status |
|--------|-------------|--------|
| code_review | Automated code analysis | Production |
| database | PostgreSQL query access | Production |
| filesystem | Shared file access | Production |
| slack_notify | Slack notifications | Production |
| doc_search | Documentation search | Production |

## Deployment

MCP servers are deployed to the AI assistant platform via the CI/CD pipeline.
Changes pushed to `main` are automatically pulled and deployed every 60 seconds.

## Development

```bash
cd servers/
python -m pytest tests/
```

Contact: jordan.torres@megacorpai.com (DevOps)
# final push test
