from typing import Dict, Any

DB_CONFIG: Dict[str, Any] = {
    "connections": {
        "default": "sqlite://db.sqlite3"
    },
    "apps": {
        "models": {
            "models": ["app.models.models"],
            "default_connection": "default",
        }
    },
    "routers": []
} 