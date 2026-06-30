from django.urls import path

from .views import (
    category_average_price,
    create_my_service_photo,
    create_service,
    delete_my_service,
    delete_my_service_photo,
    get_my_service,
    service_photo_proxy,
    service_categories,
    services_route_check,
    update_my_service,
    update_my_service_prices,
)

urlpatterns = [
    path("", services_route_check, name="services-route-check"),
    path("categories/", service_categories, name="services-categories"),
    path("category-avg-price/", category_average_price, name="services-category-average-price"),
    path("service/", create_service, name="services-create-service"),
    path("service/me/", get_my_service, name="services-get-my-service"),
    path("service/me/update/", update_my_service, name="services-update-my-service"),
    path("service/me/delete/", delete_my_service, name="services-delete-my-service"),
    path("service/prices/", update_my_service_prices, name="services-update-my-service-prices"),
    path("service/photos/", create_my_service_photo, name="services-create-my-service-photo"),
    path("service/photos/<int:photo_id>/", delete_my_service_photo, name="services-delete-my-service-photo"),
    path("service/photo/<int:photo_id>/", service_photo_proxy, name="services-photo-proxy"),
]
