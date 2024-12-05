"""Plugin URL configuration."""

from django.urls import path

from . import views

app_name = "imperial_coldfront_plugin"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "group/<int:user_pk>/members/", views.group_members_view, name="group_members"
    ),
    path("send_group_invite/", views.send_group_invite, name="send_group_invite"),
    path(
        "accept_group_invite/<str:token>/",
        views.accept_group_invite,
        name="accept_group_invite",
    ),
]
