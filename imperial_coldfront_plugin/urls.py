"""Plugin URL configuration."""

from django.urls import path

from . import views

app_name = "imperial_coldfront_plugin"

urlpatterns = [
    path(
        "group/<int:group_pk>/members/",
        views.group_members_view,
        name="group_members",
    ),
    path(
        "check_access/",
        views.check_access,
        name="check_access",
    ),
    path(
        "send_group_invite/<int:group_pk>",
        views.send_group_invite,
        name="send_group_invite",
    ),
    path(
        "accept_group_invite/<str:token>/",
        views.accept_group_invite,
        name="accept_group_invite",
    ),
    path(
        "remove_user/<int:group_membership_pk>/",
        views.remove_group_member,
        name="remove_group_member",
    ),
    path("active_users/", views.get_active_users, name="get_active_users"),
    path("groups/", views.get_group_data, name="get_group_data"),
    path("user_search/<int:group_pk>", views.user_search, name="user_search"),
    path(
        "make_manager/<int:group_membership_pk>/",
        views.make_group_manager,
        name="make_manager",
    ),
    path(
        "remove_manager/<int:group_membership_pk>/",
        views.remove_group_manager,
        name="remove_manager",
    ),
    path(
        "extend_membership/<int:group_membership_pk>/",
        views.group_membership_extend,
        name="extend_membership",
    ),
    path(
        "research-group/create/",
        views.research_group_terms_view,
        name="research_group_create",
    ),
    path(
        "create_rdf_allocation/",
        views.add_rdf_storage_allocation,
        name="add_rdf_storage_allocation",
    ),
]
