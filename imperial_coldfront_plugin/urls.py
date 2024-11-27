"""Plugin URL configuration."""

from django.urls import path

from .views import add_to_group, add_to_group_confirm

urlpatterns = [
    path("add_to_group/", add_to_group, name="add_to_group"),
    path("add_to_group_confirm/", add_to_group_confirm, name="add_to_group_confirm"),
]
