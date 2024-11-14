"""Plugin URL configuration."""

from django.urls import path

from . import views

urlpatterns = [
    path(
        "group/<int:user_pk>/members/", views.group_members_view, name="group_members"
    ),
]
