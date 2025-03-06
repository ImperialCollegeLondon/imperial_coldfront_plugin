"""A dummy urls.py file for testing.

This file is used to emulate the inclusion of the plugin urls.py within ColdFront's
urls.py. This ensures that the urls are correctly namespaced when looked up in
templates.
"""

import coldfront.core.portal.views as portal_views
from django.urls import include, path

urlpatterns = [
    path("", portal_views.home, name="home"),
    path("icl/", include("imperial_coldfront_plugin.urls")),
]
