"""
Compatibility shim for legacy imports
This module re-exports queue manager APIs so existing code importing
`core.scheduler` keeps working.
"""

from .queue_manager import (
    QueueManager,
    Message,
    MessageSource,
    MessagePriority,
    queue_manager,
)

# Backward-compatible alias
scheduler = queue_manager