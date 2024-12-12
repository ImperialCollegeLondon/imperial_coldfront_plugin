from django.urls import include, path

urlpatterns = [path("icl/", include("imperial_coldfront_plugin.urls"))]
