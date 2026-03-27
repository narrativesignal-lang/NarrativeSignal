"""
Free plan limits. Shared constants for validation and error messages.
Synchronize with frontend src/lib/limits.ts.
"""

# Free plan limits (paid plans can override via config later)
MAX_PORTFOLIOS = 4
MAX_ENTITIES_PER_PORTFOLIO = 4
MAX_ITEMS_PER_ENTITY = 8  # added items per entity (e.g. related instruments, widgets)
MAX_SAVED_SCHEDULES = 10
MAX_ACTIVE_SCHEDULES = 5
MAX_REPORTS = 100

# User-facing messages (returned in 4xx detail for frontend to display)
MSG_MAX_PORTFOLIOS = (
    "You have reached the maximum number of portfolios (4). Upgrade your plan to create more."
)
MSG_MAX_ENTITIES = (
    "Each portfolio can contain up to 4 entities. Upgrade your plan to add more."
)
MSG_MAX_ITEMS_PER_ENTITY = (
    "Each entity can contain up to 8 added items on the Free plan."
)
MSG_MAX_SAVED_SCHEDULES = (
    "You can save up to 10 schedules on the Free plan."
)
MSG_MAX_ACTIVE_SCHEDULES = (
    "You can activate up to 5 schedules at the same time on the Free plan."
)
MSG_MAX_REPORTS = (
    "You have reached the maximum number of reports (100). Please delete some reports before creating more."
)
