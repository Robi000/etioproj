from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import ContactRequest


FREE_DAILY_CONTACT_REQUESTS = 2
DAILY_CONTACT_REQUEST_HARD_LIMIT = 6
WEEKLY_CONTACT_REQUEST_HARD_LIMIT = 7

_COOLDOWN_TABLE_SECONDS = [0, 0, 1200, 1800, 3000, 3600]


@dataclass(frozen=True)
class ContactRequestUsageDecision:
    allowed: bool
    requests_today: int
    weekly_requests: int
    free_requests_per_day: int
    daily_hard_limit: int
    weekly_hard_limit: int
    protection_level: str
    cooldown_seconds: int
    retry_after_seconds: int
    next_request_at: datetime | None
    message: str


def evaluate_contact_request_creation(customer, now=None) -> ContactRequestUsageDecision:
    """
    Progressive protection for provider contact sharing with weekly and daily limits.
    """
    now = now or timezone.now()
    day_start, next_day_start = get_local_day_window(now)
    week_start, next_week_start = get_local_week_window(now)

    # Weekly limit check
    weekly_requests = ContactRequest.objects.filter(
        customer=customer,
        created_at__gte=week_start,
        created_at__lt=next_week_start,
    ).count()

    # Daily requests count
    todays_requests = ContactRequest.objects.filter(
        customer=customer,
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    )
    requests_today = todays_requests.count()

    # 1. Weekly Hard Limit Check (evaluated before daily limit)
    if weekly_requests >= WEEKLY_CONTACT_REQUEST_HARD_LIMIT:
        retry_after_seconds = seconds_until(now, next_week_start)
        return ContactRequestUsageDecision(
            allowed=False,
            requests_today=requests_today,
            weekly_requests=weekly_requests,
            free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
            daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
            weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
            protection_level="weekly_lock",
            cooldown_seconds=retry_after_seconds,
            retry_after_seconds=retry_after_seconds,
            next_request_at=next_week_start,
            message=(
                "Weekly contact protection limit reached. "
                "Please continue next week."
            ),
        )

    # 2. Daily Hard Limit Check
    if requests_today >= DAILY_CONTACT_REQUEST_HARD_LIMIT:
        retry_after_seconds = seconds_until(now, next_day_start)
        return ContactRequestUsageDecision(
            allowed=False,
            requests_today=requests_today,
            weekly_requests=weekly_requests,
            free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
            daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
            weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
            protection_level="daily_lock",
            cooldown_seconds=retry_after_seconds,
            retry_after_seconds=retry_after_seconds,
            next_request_at=next_day_start,
            message=(
                "Daily contact protection limit reached. "
                "Please continue tomorrow."
            ),
        )

    # 3. Free requests check
    if requests_today < FREE_DAILY_CONTACT_REQUESTS:
        return ContactRequestUsageDecision(
            allowed=True,
            requests_today=requests_today,
            weekly_requests=weekly_requests,
            free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
            daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
            weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
            protection_level="smooth",
            cooldown_seconds=0,
            retry_after_seconds=0,
            next_request_at=None,
            message="Contact request is allowed.",
        )

    # 4. Pacing Cooldown Check
    cooldown_seconds = _COOLDOWN_TABLE_SECONDS[min(requests_today, len(_COOLDOWN_TABLE_SECONDS) - 1)]
    last_request_at = todays_requests.order_by("-created_at").values_list(
        "created_at",
        flat=True,
    ).first()

    if last_request_at is None:
        return ContactRequestUsageDecision(
            allowed=True,
            requests_today=requests_today,
            weekly_requests=weekly_requests,
            free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
            daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
            weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
            protection_level="smooth",
            cooldown_seconds=0,
            retry_after_seconds=0,
            next_request_at=None,
            message="Contact request is allowed.",
        )

    next_request_at = last_request_at + timedelta(seconds=cooldown_seconds)

    if now >= next_request_at:
        return ContactRequestUsageDecision(
            allowed=True,
            requests_today=requests_today,
            weekly_requests=weekly_requests,
            free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
            daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
            weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
            protection_level=protection_level_for(requests_today),
            cooldown_seconds=cooldown_seconds,
            retry_after_seconds=0,
            next_request_at=next_request_at,
            message="Contact request is allowed after pacing cooldown.",
        )

    retry_after_seconds = seconds_until(now, next_request_at)
    return ContactRequestUsageDecision(
        allowed=False,
        requests_today=requests_today,
        weekly_requests=weekly_requests,
        free_requests_per_day=FREE_DAILY_CONTACT_REQUESTS,
        daily_hard_limit=DAILY_CONTACT_REQUEST_HARD_LIMIT,
        weekly_hard_limit=WEEKLY_CONTACT_REQUEST_HARD_LIMIT,
        protection_level=protection_level_for(requests_today),
        cooldown_seconds=cooldown_seconds,
        retry_after_seconds=retry_after_seconds,
        next_request_at=next_request_at,
        message=(
            "Contact request pacing is active to protect providers from "
            "high-volume or accidental requests."
        ),
    )


def build_contact_usage_payload(decision: ContactRequestUsageDecision) -> dict:
    return {
        "new_contact_request_allowed_now": decision.allowed,
        "requests_today": decision.requests_today,
        "weekly_requests": decision.weekly_requests,
        "free_requests_per_day": decision.free_requests_per_day,
        "daily_hard_limit": decision.daily_hard_limit,
        "weekly_hard_limit": decision.weekly_hard_limit,
        "protection_level": decision.protection_level,
        "cooldown_seconds": decision.cooldown_seconds,
        "retry_after_seconds": decision.retry_after_seconds,
        "next_request_at": decision.next_request_at,
        "message": decision.message,
    }


def protection_level_for(requests_today: int) -> str:
    if requests_today < 5:
        return "paced"
    if requests_today < 8:
        return "high_intent"
    return "heavy_protection"


def get_local_day_window(now):
    current_timezone = timezone.get_current_timezone()
    local_day = timezone.localdate(now, timezone=current_timezone)
    day_start = timezone.make_aware(
        datetime.combine(local_day, time.min),
        current_timezone,
    )
    return day_start, day_start + timedelta(days=1)


def get_local_week_window(now):
    current_timezone = timezone.get_current_timezone()
    local_now = timezone.localtime(now, timezone=current_timezone)
    local_day = local_now.date()
    monday_date = local_day - timedelta(days=local_day.weekday())
    week_start = timezone.make_aware(
        datetime.combine(monday_date, time.min),
        current_timezone,
    )
    return week_start, week_start + timedelta(weeks=1)


def seconds_until(now, target_time) -> int:
    return max(1, int((target_time - now).total_seconds()))
