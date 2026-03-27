"""
Placeholder for future email forwarding of community submissions.

When email service is integrated:
- Set COMMUNITY_SUBMISSION_EMAIL in config
- Implement actual SMTP/sendgrid/etc in forward_submission() and forward_data_request()
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def forward_submission_email(
    category: str,
    title: str,
    description: str,
    contact_info: str,
    **kwargs,
) -> None:
    """Placeholder: forward community submission to admin email. Email forwarding coming soon."""
    logger.info(
        "Community submission (email placeholder): category=%s title=%s contact=%s",
        category,
        title,
        contact_info[:50] if contact_info else "—",
    )
    # Future: send to settings.COMMUNITY_SUBMISSION_EMAIL


def forward_data_request_email(
    requested_data_name: str,
    description: str,
    source_known: bool,
    contact_info: str,
    **kwargs,
) -> None:
    """Placeholder: forward data request to admin email. Email forwarding coming soon."""
    logger.info(
        "Data request (email placeholder): name=%s source_known=%s",
        requested_data_name,
        source_known,
    )
    # Future: send to settings.COMMUNITY_DATA_REQUEST_EMAIL
