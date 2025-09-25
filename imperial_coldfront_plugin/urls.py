"""Plugin URL configuration."""

from django.urls import path

from . import views

app_name = "imperial_coldfront_plugin"

urlpatterns = [
    path(
        "create_rdf_allocation/",
        views.add_rdf_storage_allocation,
        name="add_rdf_storage_allocation",
    ),
    path(
        "load_departments/",
        views.load_departments,
        name="load_departments",
    ),
    path(
        "allocation_task_result/<str:task_id>/<str:shortname>",
        views.allocation_task_result,
        name="allocation_task_result",
    ),
    path(
        "add_dart_id/<int:allocation_pk>/",
        views.add_dart_id_to_allocation,
        name="add_dart_id",
    ),
    path("new_group/", views.project_creation, name="new_group"),
    path(
        "<int:pk>/add-users-search-results/",
        views.ProjectAddUsersSearchResultsShortnameView.as_view(),
        name="project-add-users-search-results",
    ),
]
