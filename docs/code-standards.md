# T-Station AI Code Standards

## General Guidelines

### Language & Version
- **Python**: 3.12
- **Package Manager**: uv

### File Naming
- Use **kebab-case** for file names
- Descriptive names that indicate purpose

### Code Organization
- Keep files under 200 lines
- Split large files into focused modules
- Use composition over inheritance

---

## Code Style

### Line Length
- Maximum 120 characters

### Imports
- Use ruff for import sorting
- Group: standard library, third-party, local
- Use absolute imports within package

### Type Hints
- Use type hints for parameters and return types

### Error Handling
- Use try-catch for error handling
- Log exceptions with appropriate level
- Return meaningful error messages

---

## Project Structure

```
app/
├── tstation-ai/              # Main AI service
│   ├── api/                  # API endpoints
│   ├── common/               # Shared utilities
│   ├── config/               # Configuration
│   ├── schemas/              # Pydantic models
│   ├── services/
│   │   └── tstation/
│   │       ├── agents/      # AI Agents
│   │       │   ├── a_leading_agent/
│   │       │   ├── b_discovery_agent/
│   │       │   ├── c_transaction_agent/
│   │       │   ├── d_shopping_agent/
│   │       │   ├── e_support_agent/
│   │       │   └── router.py
│   │       └── chat.py
│   └── main.py
├── tstation-be/             # Backend service
└── tstation-ui-demo/        # Demo UI
```

---

## Agent Architecture

### Directory Naming
Use prefix ordering (a_, b_, c_, ...) to control import order:

```
agents/
├── a_leading_agent/      # Orchestrator
├── b_discovery_agent/   # Recommendations
├── c_transaction_agent/ # Orders
├── d_shopping_agent/    # Price/stock
├── e_support_agent/    # Policies
└── router.py            # Domain router
```

---

## API Design

### Request/Response Models
Use Pydantic models:

```python
class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    messages: List[Message]
    stream: bool = False
    tracing_id: Optional[str] = None
```

---

## Testing

- Use pytest
- Follow AAA pattern (Arrange, Act, Assert)
- Mock external services

---

## Linting & Formatting

```bash
just lint    # Check code
just fmt     # Format code
```

---

## Documentation

Use Google-style docstrings:

```python
def function_name(param: str) -> str:
    """Short description.

    Args:
        param: Description

    Returns:
        Description
    """
    pass
```

---

## Security

- Require API key for protected endpoints
- Never commit secrets
- Use environment variables for credentials
