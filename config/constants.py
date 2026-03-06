"""Non-configurable application constants.

These values are fixed by the application design and are not overridable
via environment variables.  Deployment-specific values (ports, credentials)
belong in config/settings.py instead.
"""

# Server always binds to all interfaces inside Docker / a container.
# Exposed externally only via docker-compose port mappings.
SERVER_BIND_HOST: str = "0.0.0.0"
