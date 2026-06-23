# Test Fixtures for BRAIN Alpha Ops

This directory contains mock responses and recording/playback infrastructure for offline testing without BRAIN API access.

## Structure

```
fixtures/
├── README.md                    # This file
├── mock_brain_api.py            # Mock server for local testing
└── recorded_responses/          # Sample JSON responses per endpoint
    ├── authentication.json      # Auth token response
    ├── data_fields.json         # Field list response
    ├── data_sets.json           # Dataset list response
    ├── operators.json           # Operator list response
    ├── user_alphas.json         # User alphas response
    ├── simulation.json          # Simulation result
    └── alpha_check.json         # Alpha check result
```

## Usage

### Running the Mock Server

```python
from fixtures.mock_brain_api import MockBRAINApiServer

server = MockBRAINApiServer(port=8765)
server.start()  # Starts mock HTTP server

# Configure your client to use mock server
client = OfficialRequest(
    username="test",
    password="test",
    base_url="http://localhost:8765"
)

# ... run your tests ...

server.stop()
```

### Using Recorded Responses Directly

```python
import json
from pathlib import Path

fixtures_dir = Path(__file__).parent / "recorded_responses"

# Load a specific fixture
with open(fixtures_dir / "data_fields.json") as f:
    data_fields_response = json.load(f)
```

## Creating New Recordings

To record real API responses for use as fixtures:

1. Run the recording client against live BRAIN API
2. Save responses as JSON in `recorded_responses/`
3. Name files to match endpoint paths (e.g., `/data-fields` → `data_fields.json`)

## Extending the Mock Server

The `MockBRAINApiServer` class supports adding custom handlers:

```python
server.add_handler("/custom/endpoint", custom_handler_fn)
```

Handlers receive the request path, method, and body, and return a JSON-serializable response.
