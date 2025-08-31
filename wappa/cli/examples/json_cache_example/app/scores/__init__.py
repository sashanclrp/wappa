"""
Score modules for JSON Cache Example following SOLID principles.

Each score module handles a specific business concern:
- score_user_management: User profile and caching logic
- score_message_history: Message logging and history retrieval
- score_state_commands: /WAPPA, /EXIT command processing
- score_cache_statistics: Cache monitoring and statistics

This architecture follows the Single Responsibility and Open/Closed principles.
"""

from .score_base import ScoreBase, ScoreDependencies
from .score_cache_statistics import CacheStatisticsScore
from .score_message_history import MessageHistoryScore
from .score_state_commands import StateCommandsScore
from .score_user_management import UserManagementScore

# Available score modules for automatic discovery
AVAILABLE_SCORES = [
    UserManagementScore,
    MessageHistoryScore,
    StateCommandsScore,
    CacheStatisticsScore,
]

__all__ = [
    "ScoreBase",
    "ScoreDependencies",
    "UserManagementScore",
    "MessageHistoryScore",
    "StateCommandsScore",
    "CacheStatisticsScore",
    "AVAILABLE_SCORES",
]
