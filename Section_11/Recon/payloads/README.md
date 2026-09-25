# Megacorp One AI – Internal Knowledge Base

This knowledge base is designed for use with local LLMs to support Retrieval-Augmented Generation (RAG) on employee machines.

## Location
The shared knowledge base is available at:

`\\FILESERVER01\Knowledgebase\`

### Subdirectories
- `\logs\` – Contains log files relevant for system and process tracking.
- `\documents\` – Contains reference documents, manuals, and internal guidelines.

## Agent Access
The RAG agent is equipped with the `read_file` tool, allowing it to read and retrieve content from the knowledge base for contextual augmentation.

## Notes
- Access is **read-only** to prevent deleting or modifying files.
- IT must set up your SSH private key to use additional external services.
- For changes, please submit a ticket to IT or contact the Knowledge Management team.
