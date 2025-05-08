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
        "list_tasks/<str:group>/<int:allocation_pk>/",
        views.task_stat_view,
        name="list_tasks",
    ),
]
