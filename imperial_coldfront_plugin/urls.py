"""Plugin URL configuration."""

from django.urls import path

from . import views

app_name = "imperial_coldfront_plugin"

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "group/<int:user_pk>/members/", views.group_members_view, name="group_members"
    ),
    path("invite_to_group/", views.invite_to_group, name="invite_to_group"),
    path("accept_invite/<str:token>/", views.accept_invite, name="accept_invite"),
]
