# Vanna for Cypy

A Cypy port of [Vanna](https://github.com/vanna-ai/vanna) — the AI-powered text-to-SQL framework.

## Why Cypy?

Vanna in Python relies on dynamic typing and async I/O. The Cypy version leverages:

- **Static typing** — compile-time error detection via `cypyc`
- **struct** — zero-overhead value types replacing dataclasses/pydantic models
- **trait** — explicit interfaces replacing ABC/Protocol
- **compile to Cython/C** — native performance for SQL execution and data processing
- **defer/guard** — ergonomic resource management and preconditions

## Architecture

```
vanna/
├── core/                    # Core framework types
│   ├── errors.cypy          # Error types
│   ├── user.cypy            # User, UserResolver, RequestContext
│   ├── components.cypy      # UI component system (DataFrames, charts, notifications)
│   ├── tool.cypy            # Tool trait, ToolContext, ToolResult
│   ├── registry.cypy        # ToolRegistry (typed tool dispatch)
│   └── agent.cypy           # Agent orchestrator
├── capabilities/            # Abstract capability interfaces
│   └── sql_runner.cypy      # SqlRunner trait
├── tools/                   # Concrete tool implementations
│   ├── run_sql.cypy         # SQL execution tool
│   └── visualize_data.cypy  # Data visualization tool
└── integrations/            # Database and LLM integrations (future)
    └── sqlite.cypy          # SQLite SqlRunner implementation
```

## Status

🚧 Work in progress — this project is also used to stress-test the `cypyc` compiler and
discover/fix bugs during real-world library porting.

## Build

```bash
cypyc build Find_BUG/Vanna --check-only   # type-check only
cypyc build Find_BUG/Vanna                 # full build
```
