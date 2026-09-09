# OpenResearchGraph

OpenResearchGraph is a traceable six-agent workflow for industry research and data Q&A. It combines a LangGraph state machine, recursive evidence retrieval, guarded text-to-SQL, two-layer memory, checkpoints, background execution and Server-Sent Events.

Repository: [github.com/wjarchy/OpenResearchGraph](https://github.com/wjarchy/OpenResearchGraph)

It runs without an API key by using a deterministic demo provider. See the [Chinese README](README.md) for setup, architecture and project boundaries.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
openresearchgraph
```

Open <http://localhost:8000> and inspect the API at <http://localhost:8000/docs>.

## License

MIT
