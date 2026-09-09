# OpenResearchGraph

OpenResearchGraph is a traceable six-agent workflow for industry research and data Q&A. It combines a LangGraph state machine, recursive evidence retrieval, guarded text-to-SQL, two-layer memory, checkpoints, background execution and Server-Sent Events.

Repository: [github.com/wjarchy/OpenResearchGraph](https://github.com/wjarchy/OpenResearchGraph)

It runs without an API key by using a deterministic demo provider. See the [Chinese README](README.md) for setup, architecture and project boundaries.

The committed benchmark contains 520 deterministic tasks. The current synthetic run reaches 100% retrieval relevance, 11% invalid tool calls, 100% structured-output success and 100% complex-workflow completion against gates of 74%, 11%, 80% and 82%. These are regression results, not production accuracy claims.

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
