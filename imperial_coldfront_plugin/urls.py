"""Plugin URL configuration."""

from django.urls import path

from . import views

urlpatterns = [
    path(
        "group/<int:user_pk>/members/", views.group_members_view, name="group_members"
    ),
    path(
        "research-group/create/",
        views.research_group_terms_view,
        name="research_group_create",
    ),
]
