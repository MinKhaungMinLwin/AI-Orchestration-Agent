# T-Station AI Code Standards

This document outlines the code standards, conventions, and best practices for the T-Station AI project.

## General Guidelines

### Language & Version

- **Language**: Python 3.12
- **Package Manager**: uv (see `pyproject.toml`)

### File Naming

- Use **kebab-case** for file names
- Use descriptive names that indicate purpose
- Examples: `detect_language.py`, `example_question.py`, `load_faqs_to_qdrant.py`

### Code Organization

- Keep individual code files under 200 lines
- Split large files into smaller, focused components/modules
- Use composition over inheritance
- Extract utility functions into separate modules

---

## Code Style

### Line Length

- Maximum 120 characters per line

### Imports

- Use `ruff` for import sorting
- Group imports: standard library, third-party, local
- Use absolute imports within the package

### Type Hints

- Use type hints for function parameters and return types
- Use `Optional` instead of `Union` with `None`

```python
# Good
def process_request(request: ChatRequest) -> ChatResponse:
    ...

def get_user(user_id: Optional[str] = None) -> Optional[User]:
    ...

# Avoid
def process_request(request) -> ChatResponse:
    ...

def get_user(user_id=None):
    ...
```

### Error Handling

- Use try-catch for error handling
- Log exceptions with appropriate level
- Return meaningful error messages

```python
try:
    result = process_data(data)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception:
    logger.exception("Error processing data")
    raise HTTPException(status_code=500, detail="Internal server error")
```

---

## Project Structure

```
app/
├── tstation-ai/              # Main AI service
│   ├── api/                  # API route handlers
│   │   ├── monitoring.py     # Health checks, metrics
│   │   ├── router.py         # Main router
│   │   └── tstation/         # T-Station endpoints
│   ├── common/               # Shared utilities
│   │   ├── curr_time.py
│   │   ├── detect_language.py
│   │   ├── openai.py
│   │   └── s3.py
│   ├── config/               # Configuration
│   │   ├── env.py
│   │   ├── log.py
│   │   ├── sec.py
│   │   └── tracing.py
│   ├── schemas/              # Pydantic models
│   │   └── tstation/
│   ├── services/             # Business logic
│   │   └── tstation/
│   │       ├── agents/      # AI Agents
│   │       │   ├── a_leading_agent/
│   │       │   ├── b_discovery_agent/
│   │       │   ├── faq_agent/
│   │       │   ├── store_agent/
│   │       │   └── router.py
│   │       ├── chat.py
│   │       └── example_question.py
│   ├── static/              # Static files
│   ├── main.py             # Entry point
│   └── requirements.txt
├── tstation-be/             # Backend service
│   ├── app/routers/        # API routers
│   ├── tests/              # Tests
│   └── main.py
└── tstation-ui-demo/       # Demo UI
```

---

## Agent Architecture

### Directory Naming

Agent directories use **prefix ordering** (a_, b_, c_, ...) to control import order:

```
agents/
├── a_leading_agent/    # Primary orchestrator (imported first)
├── b_discovery_agent/ # Discovery agent
├── c_faq_agent/       # FAQ agent (if renamed)
└── router.py          # Domain router
```

### Agent Structure

Each agent should follow this pattern:

```python
# agent.py
class AgentName:
    def __init__(self, config: AgentConfig):
        self.config = config

    async def run(self, input_data: Input) -> Output:
        # Agent logic
        pass
```

---

## API Design

### Endpoints

- Use RESTful patterns
- Use appropriate HTTP methods (GET, POST, PUT, DELETE)
- Include OpenAPI documentation in docstrings

```python
@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint for T-Station AI.

    Parameters:
 session_id (str): Session        - ID
        - user_id (str): User ID
        - messages (list): Message history
        - stream (bool): Enable streaming

    Returns:
        - response (str): AI response
    """
    pass
```

### Request/Response Models

Use Pydantic models for validation:

```python
class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    messages: List[Message]
    stream: bool = False
    tracing_id: Optional[str] = None
    metadata: dict = {}
```

---

## Configuration

### Environment Variables

- Store sensitive data in environment variables
- Use `.env.example` for required variables
- Never commit `.env` files

### Settings Pattern

```python
# config/env.py
from pydantic_settings import BaseSettings
from enum import Enum

class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"

class Settings(BaseSettings):
    ENV: Environment = Environment.DEV
    API_SECRET_KEY: str
    # ... other settings
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_price.py
└── test_shop.py
```

### Test Guidelines

- Use pytest
- Follow AAA pattern (Arrange, Act, Assert)
- Mock external services

---

## Linting & Formatting

### Tools

- **ruff**: Linting and formatting
- **isort**: Import sorting

### Commands

```bash
just lint    # Check code
just fmt     # Format code
```

### Configuration

See `ruff.toml` for linting rules.

---

## Documentation

### Docstrings

Use Google-style docstrings:

```python
def function_name(param: str) -> str:
    """Short description of function.

    Longer description if needed.

    Args:
        param: Description of parameter

    Returns:
        Description of return value

    Raises:
        ValueError: When something is wrong
    """
    pass
```

---

## Security

### API Authentication

- Require API key for protected endpoints
- Use dependency injection for auth:

```python
from config.sec import get_api_key

@router.get("/protected", dependencies=[Depends(get_api_key)])
async def protected_endpoint():
    pass
```

### Sensitive Data

- Never log sensitive data
- Never commit secrets
- Use environment variables for credentials
