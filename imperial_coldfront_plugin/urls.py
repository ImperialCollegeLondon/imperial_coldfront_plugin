"""Plugin URL configuration."""

from django.urls import path

from .views import accept_invite, invite_to_group

urlpatterns = [
    path("invite_to_group/", invite_to_group, name="invite_to_group"),
    path("accept_invite/<str:token>/", accept_invite, name="accept_invite"),
]
