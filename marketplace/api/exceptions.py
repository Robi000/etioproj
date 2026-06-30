import logging
from rest_framework.views import exception_handler

logger = logging.getLogger("marketplace")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    request = context.get("request")
    view = context.get("view")

    logger.exception(
        "API exception occurred. path=%s view=%s error=%s",
        getattr(request, "path", None),
        view.__class__.__name__ if view else None,
        str(exc),
    )

    if response is not None:
        response.data = {
            "success": False,
            "error": response.data,
            "status_code": response.status_code,
        }

    return response
