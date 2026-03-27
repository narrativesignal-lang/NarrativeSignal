/**
 * Free plan limits. Keep in sync with backend app/core/limits.py.
 * Used for UI counts, disabling buttons, and to show user-facing messages.
 */

export const FREE_PLAN_LIMITS = {
  MAX_PORTFOLIOS: 4,
  MAX_ENTITIES_PER_PORTFOLIO: 4,
  MAX_ITEMS_PER_ENTITY: 8,
  MAX_SAVED_SCHEDULES: 10,
  MAX_ACTIVE_SCHEDULES: 5,
  MAX_REPORTS: 100,
} as const;

export const LIMIT_MESSAGES = {
  MAX_PORTFOLIOS:
    "You have reached the maximum number of portfolios (4). Upgrade your plan to create more.",
  MAX_ENTITIES:
    "Each portfolio can contain up to 4 entities. Upgrade your plan to add more.",
  MAX_ITEMS_PER_ENTITY:
    "Each entity can contain up to 8 added items on the Free plan.",
  MAX_SAVED_SCHEDULES:
    "You can save up to 10 schedules on the Free plan.",
  MAX_ACTIVE_SCHEDULES:
    "You can activate up to 5 schedules at the same time on the Free plan.",
  MAX_REPORTS:
    "You have reached the maximum number of reports (100). Please delete some reports before creating more.",
} as const;
