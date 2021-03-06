from django.conf.urls.defaults import *
from views import profile, profiles, profile_statistics, profile_redirect
from forms import UserProfileDetailForm
from turan.views import create_object

urlpatterns = patterns('',
    url(r'^username_autocomplete/$', 'autocomplete_app.views.username_autocomplete_friends', name='profile_username_autocomplete'),
    url(r'^$', profiles, name='profile_list'),
    url(r'^redirect/$', profile_redirect, name='profile_redirect'),
    url(r'^(?P<username>[\w\._-]+)/$', profile, name='profile_detail'),
    url(r'^(?P<username>[\w\._-]+)/statistics/$', profile_statistics, name='profile_statistics'),
    url(r'^(?P<username>[\w\._-]+)/statistics/(?P<year>\d+)$', profile_statistics, name='profile_statistics'),
    url(r'^(?P<username>[\w\._-]+)/statistics/(?P<year>\d+)/(?P<month>\d+)$', profile_statistics, name='profile_statistics'),
)
urlpatterns += patterns('',
    url(r'^userprofiledetail/create/$', create_object, {'login_required': True, 'form_class': UserProfileDetailForm, 'profile_required': True},name='userprofiledetail_create'),
)
