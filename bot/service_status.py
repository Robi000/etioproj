from services.models import ServiceProfile


STATUS_LABELS = {
    ServiceProfile.ApprovalStatus.PENDING: "⏳ Pending admin review",
    ServiceProfile.ApprovalStatus.APPROVED: "✅ Approved",
    ServiceProfile.ApprovalStatus.REJECTED: "❌ Rejected",
    ServiceProfile.ApprovalStatus.SUSPENDED: "⏸ Suspended",
}

STATUS_NOTES = {
    ServiceProfile.ApprovalStatus.PENDING: (
        "Your application is waiting for admin review. You will receive a Telegram "
        "message as soon as it is approved."
    ),
    ServiceProfile.ApprovalStatus.APPROVED: (
        "Your service can appear in discovery while visibility is ON."
    ),
    ServiceProfile.ApprovalStatus.REJECTED: (
        "Your service is not visible in discovery. Please contact admin or update "
        "your draft before trying again."
    ),
    ServiceProfile.ApprovalStatus.SUSPENDED: (
        "Your service is temporarily hidden from discovery."
    ),
}


def get_provider_service(telegram_user_id: int) -> ServiceProfile | None:
    return (
        ServiceProfile.objects.select_related("provider", "category", "approved_by")
        .prefetch_related("prices", "photos")
        .filter(provider__telegram_id=telegram_user_id)
        .first()
    )


def build_provider_service_status_text(service: ServiceProfile | None) -> str:
    if service is None:
        return (
            "📋 My Service\n\n"
            "No submitted service application was found yet.\n\n"
            "Press 🛠 Create Service from /start to begin your provider registration."
        )

    status_label = STATUS_LABELS.get(service.approval_status, service.approval_status)
    status_note = STATUS_NOTES.get(service.approval_status, "")
    visibility = "ON" if service.visibility_status == ServiceProfile.VisibilityStatus.ON else "OFF"
    price_count = service.prices.count()
    photo_count = service.photos.count()

    lines = [
        "📋 My Service Status",
        "",
        f"Service: {service.title}",
        f"Category: {service.category.name}",
        f"Application: {status_label}",
        f"Visibility: {visibility}",
        f"Prices: {price_count}",
        f"Photos: {photo_count}/3",
    ]

    if service.approved_at:
        lines.append(f"Approved at: {service.approved_at:%Y-%m-%d %H:%M}")

    if status_note:
        lines.extend(["", status_note])

    return "\n".join(lines)


def build_service_approval_notification_text(service: ServiceProfile) -> str:
    return (
        "✅ Your service application has been approved!\n\n"
        f"Service: {service.title}\n"
        f"Category: {service.category.name}\n\n"
        "Customers can now discover you while your visibility is ON."
    )


def build_service_rejection_notification_text(service: ServiceProfile) -> str:
    return (
        "❌ Your service application was rejected.\n\n"
        f"Service: {service.title}\n"
        f"Category: {service.category.name}\n\n"
        "Your service is not visible in discovery. Please contact admin if you need help."
    )
