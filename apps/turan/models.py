#!/usr/bin/env python
# -*- coding: UTF-8
from django.db import models
from django.db.models import Avg, Max, Min, Count, Variance, StdDev, Sum
from django.db.models.signals import pre_save, post_save, post_delete
from django.contrib.contenttypes.models import ContentType

from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext
from django.contrib.auth.models import User
from django.contrib.humanize.templatetags.humanize import naturalday
from django.core.urlresolvers import reverse
#from django.template.defaultfilters import slugify
from turan.templatetags.turan_extras import u_slugify as slugify
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.contrib.contenttypes import generic
from django.core.files.base import ContentFile
from tagging.fields import TagField
import types
from os.path import join
import re

import urllib
import json
from photos.models import Pool, Image

from celery.task.sets import subtask
from datetime import datetime
import datetime

from durationfield import DurationField

from gpxparser import GPXParser, proj_distance
from gpxwriter import GPXWriter

from tasks import create_simplified_gpx, create_png_from_gpx, create_gpx_from_details, \
        merge_sensordata, calculate_ascent_descent_gaussian, calculate_best_efforts, \
        parse_and_calculate, filldistance, hr2zone, watt2zone, \
        getgradients

if "notification" in settings.INSTALLED_APPS:
    from notification import models as notification
else:
    notification = None

gpxstore = FileSystemStorage(location=settings.GPX_STORAGE)
AUTOROUTE_DESCRIPTION = "Autoroute"
GEOURL = "http://api.geonames.org/findNearbyPlaceNameJSON?formatted=true&username=turan&style=full&lng=%f&lat=%f"

class ExerciseType(models.Model):

    name = models.CharField(max_length=40)
    logo = models.ImageField(upload_to='exerciselogos', blank=True, storage=gpxstore)
    altitude = models.BooleanField(blank=True, default=0)
    slopes = models.BooleanField(blank=True, default=0)

    def __unicode__(self):
        return ugettext(self.name)

    def __repr__(self):
        return unicode(self.name)

    def icon(self):
        # FIXME use media url
        if self.logo:
            return settings.MEDIA_URL + 'turan/%s' %(self.logo)
        return ''

    class Meta:
        verbose_name = _("Exercise Type")
        verbose_name_plural = _("Exercise Types")
        ordering = ('name',)

class EquipmentType(models.Model):
    name = models.CharField(max_length=140)
    description = models.TextField(_('Description'), help_text=_('Equipment description'), blank=True, null=True)
    icon = models.ImageField(upload_to='equipment', null=True, blank=True, storage=gpxstore)

    def __unicode__(self):
        return unicode(self.name)

    class Meta:
        verbose_name = _("Equipment Type")
        verbose_name_plural = _("Equipment Types")

class Equipment(models.Model):
    user = models.ForeignKey(User)
    equipmenttype = models.ForeignKey(EquipmentType)
    image = models.ImageField(upload_to='equipment', blank=True, storage=gpxstore)
    url = models.URLField(_('External URL'), blank=True, help_text=_('Added info in external URL'))
    brand = models.CharField(_('Brand'), max_length=140)
    model = models.CharField(_('Model'), max_length=140)
    weight = models.FloatField(_('Weight'), blank=True, null=True, help_text=_('in kg'))
    riding_weight = models.FloatField(_('Weight when in use'), default=0, blank=True, help_text=_('weight in kg when riding, used for power estimations. Include bottles, clothes, etc'))
    notes = models.TextField(_('Notes'), help_text=_('Equipment description'), blank=True, null=True)
    aquired = models.DateField(_('Aquired'), help_text=_('Date you aquired the equipment'))
    exercise_type = models.ForeignKey(ExerciseType, verbose_name=_('Exercise type'), blank=True, null=True)

    def __unicode__(self):
        return unicode('%s %s %s' %(self.equipmenttype, self.brand, self.model))

    class Meta:
        verbose_name = _("Equipment")
        verbose_name_plural = _("Equipment")
        ordering = ('-aquired',)

    def get_distance(self):
        ''' Get the exercises with routes and sum the distance '''
        return self.exercise_set.exclude(route__isnull=True).aggregate(sum=Sum('route__distance'))['sum']

    def get_absolute_url(self):
        return reverse('profile_redirect')

    def get_weight(self):
        ''' Returns weight, using riding weight if given, or add 3kg for normal equipment if not '''
        if self.riding_weight:
            return self.riding_weight
        elif self.weight:
            return self.weight + 3

class ComponentType(models.Model):
    name = models.CharField(max_length=140)
    description = models.TextField(_('Description'), help_text=_('Component description'), blank=True, null=True)

    class Meta:
        verbose_name = _("Component Type")
        verbose_name_plural = _("Component Types")

    def __unicode__(self):
        return unicode(self.name)

class Component(models.Model):
    equipment= models.ForeignKey(Equipment)
    componenttype = models.ForeignKey(ComponentType)
    brand = models.CharField(_('Brand'), max_length=140)
    model = models.CharField(_('Model'), max_length=140)
    weight = models.FloatField(_('Weight'), default=0, blank=True, help_text=_('in kg'))
    added = models.DateField(_('Added'))
    removed = models.DateField(_('Removed'),null=True,blank=True)
    notes = models.TextField(_('Notes'), help_text=_('Component description'), blank=True, null=True)

    def __unicode__(self):
        return unicode('%s %s %s' %(self.componenttype, self.brand, self.model))

    class Meta:
        verbose_name = _("Component")
        verbose_name_plural = _("Components")

    def get_distance(self):
        ''' Get the exercises in the daterange with routes and sum the distance '''
        end_date = self.removed
        if not end_date:
            end_date = datetime.date.today()
        return Exercise.objects\
                .filter(equipment=self.equipment)\
                .exclude(route__isnull=True)\
                .filter(date__range=(self.added, end_date))\
                .aggregate(sum=Sum('route__distance'))['sum']


class RouteManager(models.Manager):
    ''' Primary purpose to remove the /dev/null route. Will also hide "one time routes" '''

    def get_query_set(self):
        # TODO, this needs to be a fixture, with a fixed ID
        return super(RouteManager, self).get_query_set().exclude(pk=24)#.filter(single_serving=0)


class Route(models.Model):
    name = models.CharField(_('Name'), max_length=160, blank=True, null=True, help_text=_('for example Opsangervatnet'))
    distance = models.FloatField(_('Distance'),help_text=_('in km'), default=0)
    description = models.TextField(_('Description'), help_text=_('route description'))
    route_url = models.URLField(_('External URL'), blank=True, help_text=_('Added info for route in external URL')) # gmaps?
    gpx_file = models.FileField(upload_to='gpx', blank=True, storage=gpxstore)
    ascent = models.IntegerField(_('Ascent'), blank=True, null=True) # m
    descent = models.IntegerField(_('Descent'), blank=True, null=True) # m
    max_altitude = models.IntegerField(_('Maximum altitude'), blank=True, null=True) # m
    min_altitude = models.IntegerField(_('Minimum altitude'), blank=True, null=True) # m

    start_lat = models.FloatField(blank=True, default=0.0)
    start_lon = models.FloatField(blank=True, default=0.0)
    end_lat = models.FloatField(blank=True, default=0.0)
    end_lon = models.FloatField(blank=True, default=0.0)

    created = models.DateTimeField(editable=False,auto_now_add=True,null=True)
    single_serving = models.BooleanField(blank=True, default=0)

    tags = TagField()

    objects = RouteManager()

    def save(self, force_insert=False, force_update=False):
        # If we have gpx file set but not start_lat set, parse gpx and set start and end positions
        if self.gpx_file:
            if not self.start_lat or not self.distance or not self.ascent:
                g = GPXParser(self.gpx_file.file)
                if g:
                    # set coordinates for route if it doesn't exist
                    if not self.start_lat:
                        self.start_lon = g.start_lon
                        self.start_lat = g.start_lat
                        self.end_lon = g.end_lon
                        self.end_lat = g.end_lat
                    if not self.distance:
                        # distance calculated in meters in parser
                        self.distance = g.distance/1000.0
                    if not self.ascent:
                        self.ascent = g.ascent
                        self.descent = g.descent
        # No name, possibly autogenerated route, try and set name
        if not self.name:
            self.set_geo_title()
        # Check for single serving that really are not
        if self.single_serving and self.exercise_set.count() > 1:
            self.single_serving = False
        elif not self.single_serving and self.description == AUTOROUTE_DESCRIPTION and self.exercise_set.count() < 2:
            self.single_serving = True
        super(Route, self).save(force_insert, force_update)
        if self.gpx_file:
            # generate svg if it doesn't exist (after save, it uses id for filename)
            filename = 'svg/%s.png' %self.id
            if not gpxstore.exists(filename):
                create_png_from_gpx.delay(self.gpx_file.path, filename)

            # generate simplified gpx to use as layer, for faster loading
            filename = 'gpx/%s.simpler.gpx' %self.id
            if not gpxstore.exists(filename):
                create_simplified_gpx.delay(self.gpx_file.path, filename)

    def set_geo_title(self):
        # Check if route is autogenerated
        if self.description == AUTOROUTE_DESCRIPTION:
            title = self.get_start_location_name()
            if title:
                self.name = title

    def __unicode__(self):
        if self.name:
            return self.name
        else:
            return ("Unnamed trip")

    def get_simplegpx_url(self):
        url = None
        if self.gpx_file:
            filename = 'gpx/%s.simpler.gpx' %self.id
            if gpxstore.exists(filename):
                url = filename
                #//url = '/'.join(self.gpx_file.url.split('/')[0:-2]) + '/' + filename
            else:
                url = self.gpx_file
        return url

    def get_absolute_url(self):
        url =  reverse('route', kwargs={ 'object_id': self.id })
        if self.name:
            url += '/' + slugify(self.name)
        return url

    def get_svg_url(self):
        if self.gpx_file:
            filename = 'svg/%s.svg' %self.id
            #return gpxstore.url(filename) Broken ?
            return '%sturan/%s' %(settings.MEDIA_URL, filename)
        else:
            return ''

    def get_png_url(self):
        if self.gpx_file:
            filename = 'svg/%s.png' %self.id
            #return gpxstore.url(filename) Broken ?
            return '%sturan/%s' %(settings.MEDIA_URL, filename)
        return '/empty.gif'

    class Meta:
        verbose_name = _("Route")
        verbose_name_plural = _("Routes")
        ordering = ('-created','name')

    def get_trips(self):
        return self.exercise_set.select_related('route', 'user').order_by('duration')

    def get_photos(self):
        ct = ContentType.objects.get_for_model(self)
        return [pool.photo for pool in Pool.objects.filter(content_type=ct, object_id=self.id)]

    def add_photo(self, photo):
        p = Pool(content_object=self, image=photo)
        p.save()

    @property
    def tripcount(self):
        ''' used in triplist, nice for sorting '''
        return len(self.get_trips())

    def get_start_location_name(self):
        lon1, lat1 = self.start_lon, self.start_lat
        start_town = ''
        if lon1 and lat1:
            try:
                f = urllib.urlopen(GEOURL % (self.start_lon, self.start_lat,))
                start = json.load(f)["geonames"][0]
                if start["countryCode"] != "NO":
                    return start["toponymName"]
            except:
                pass
            s_distance = 99999999
            for loc in find_close_locations(lon1, lat1):
                this_distance = proj_distance(lat1, lon1, loc.lat, loc.lon)
                if this_distance < s_distance:
                    start_town = loc.town
                    s_distance = this_distance
        return start_town

    def get_geo_title(self):
        lon1, lat1 = self.start_lon, self.start_lat
        lon2, lat2 = self.end_lon, self.end_lat
        if lon1 and lat1 and lat2 and lon2:
            s_distance = 99999999
            farthest = self.find_farthest_pos_from_start()
            if not farthest: return None # FIXME later why does this happen /garmin_connect_66078400.tcx
            farthest_lon, farthest_lat = farthest
            f_distance = 99999999
            e_distance = 99999999
            start_town = ''
            farthest_town = ''
            end_town = ''

            for loc in find_close_locations(lon1, lat1):
                this_distance = proj_distance(lat1, lon1, loc.lat, loc.lon)
                if this_distance < s_distance:
                    start_town = loc.town
                    s_distance = this_distance
            for loc in find_close_locations(farthest_lon, farthest_lat):
                if farthest_lon and farthest_lat:
                    this_distance = proj_distance(farthest_lat, farthest_lon, loc.lat, loc.lon)
                    if this_distance < f_distance:
                        farthest_town = loc.town
                        f_distance = this_distance
            for loc in find_close_locations(lon2, lat2):
                this_distance = proj_distance(lat2, lon2, loc.lat, loc.lon)
                if this_distance < e_distance:
                    end_town = loc.town
                    e_distance = this_distance
            if farthest_town:
                if start_town == end_town and farthest_town != end_town:
                    return '%s %s %s' %(start_town, farthest_town, end_town)
                if start_town != farthest_town != end_town:
                    return '%s %s %s' %(start_town, farthest_town, end_town)
                if start_town == farthest_town == end_town:
                    return start_town
                elif start_town == farthest_town:
                    return '%s %s' %(start_town, end_town)
                elif end_town == farthest_town:
                    return '%s %s' %(start_town, end_town)
                if start_town == end_town:
                    return start_town
            else:
                if start_town == end_town:
                    return start_town
                return '%s %s' %(start_town, end_town)

    def find_farthest_pos_from_start(self):
        if self.gpx_file:
            details = GPXParser(self.gpx_file).entries
            if details:
                lon, lat = details[0].lon, details[0].lat
                distance = 0
                max_lon, max_lat = 0, 0
                for d in details:
                    this_lon, this_lat = d.lon, d.lat
                    if this_lon and this_lat:
                        this_distance = proj_distance(lat, lon, this_lat, this_lon)
                        if this_distance > distance:
                            distance = this_distance
                            max_lon, max_lat = this_lon, this_lat
                return max_lon, max_lat


class ExerciseManager(models.Manager):
    ''' Some permission related purposes '''

    def get_query_set(self):
        return super(ExerciseManager, self).get_query_set().exclude(exercise_permission='N')

permission_choices = (
            ('A', _('All')),
            ('F', _('Friends')),
            ('N', _('Only myself')),
                    )
live_states = (
            ('F', _('Finished')),
            ('P', _('Paused')),
            ('L', _('Live')),
)

class Exercise(models.Model):

    user = models.ForeignKey(User)
    exercise_type = models.ForeignKey(ExerciseType, verbose_name=_('Exercise type'), default=13) # FIXME hardcoded to cycling
    route = models.ForeignKey(Route, blank=True, null=True, help_text=_("Search existing routes"))
    duration = DurationField(_('Duration'), blank=True, default=0, help_text='18h 30m 23s 10ms 150mis')
    date = models.DateField(_('Date'), blank=True, null=True, help_text=_("year-mo-dy"))
    time = models.TimeField(_('Start time'), blank=True, null=True, help_text="00:00:00")

    comment = models.TextField(_('Comment'), blank=True)
    url = models.URLField(_('External URL'), blank=True)

    avg_speed = models.FloatField(blank=True, null=True) #kmt
    avg_cadence = models.IntegerField(blank=True, null=True) # rpm
    avg_pedaling_cad = models.IntegerField(blank=True, null=True) # rpm
    avg_power = models.IntegerField(blank=True, null=True) # W
    avg_pedaling_power = models.IntegerField(blank=True, null=True) # W
    normalized_power = models.IntegerField(blank=True, null=True) # W 
    xPower = models.IntegerField(blank=True, null=True) # W 
    normalized_hr = models.IntegerField(blank=True, null=True) # W 

    max_speed = models.FloatField(blank=True, null=True) #kmt
    max_cadence = models.IntegerField(blank=True, null=True) # rpm
    max_power = models.IntegerField(blank=True, null=True) # W

    avg_hr = models.IntegerField(blank=True, null=True) # bpm 
    max_hr = models.IntegerField(blank=True, null=True) # bpm 

    kcal = models.IntegerField(blank=True, null=True, default=0, help_text=_('Only needed for Polar products'))
    temperature = models.FloatField(blank=True, null=True, help_text=_('Celsius'))
    min_temperature = models.FloatField(blank=True, null=True, help_text=_('Celsius'))
    max_temperature = models.FloatField(blank=True, null=True, help_text=_('Celsius'))
    sensor_file = models.FileField(_('Exercise file'), upload_to='sensor', blank=True, storage=gpxstore, help_text=_('File from equipment from Garmin/Polar/other (.fit, .tcx, .gpx, .hrm, .gmd, .csv, .xml)'))

    exercise_permission = models.CharField(_('Exercise permission'), max_length=1, choices=permission_choices, default='A', )
    live_state = models.CharField(max_length=1, choices=live_states, default='F', blank=True, null=True)
    equipment = models.ForeignKey(Equipment, help_text=_('Select the equipment used for this exercise, for statistics and tracking'), verbose_name=_('Equipment'), null=True, blank=True)

    object_id = models.IntegerField(null=True)
    content_type = models.ForeignKey(ContentType, null=True)
    group = generic.GenericForeignKey("object_id", "content_type")

    tags = TagField(verbose_name=_('Tags'), help_text='f.eks. sol regn uhell punktering')

    max_speed_lat = models.FloatField(blank=True, null=True, default=0.0)
    max_speed_lon = models.FloatField(blank=True, null=True, default=0.0)
    max_power_lat = models.FloatField(blank=True, null=True, default=0.0)
    max_power_lon = models.FloatField(blank=True, null=True, default=0.0)
    max_cadence_lat = models.FloatField(blank=True, null=True, default=0.0)
    max_cadence_lon = models.FloatField(blank=True, null=True, default=0.0)
    max_hr_lat = models.FloatField(blank=True, null=True, default=0.0)
    max_hr_lon = models.FloatField(blank=True, null=True, default=0.0)
    max_altitude_lat = models.FloatField(blank=True, null=True, default=0.0)
    max_altitude_lon = models.FloatField(blank=True, null=True, default=0.0)

    #objects = models.Manager() # default manager

    #testm = CycleTripManager()
#    objects = ExerciseManager()

    def get_details(self):
        return self.exercisedetail_set

    def save(self, *args, **kwargs):
        super(Exercise, self).save(*args, **kwargs)
        if self.sensor_file:
            if not self.route and str(self.exercise_type) not in ("Puls", "Spinning",  "Rollers", 'Svømming', 'Volleyball', 'Basketball', 'Elliptical'):
                r = Route()
                r.description = AUTOROUTE_DESCRIPTION
                r.single_serving = True
                r.save()
                self.route = r
        # set avg_speed if distance and duration is given
        if self.route and self.route.distance and self.duration and not self.avg_speed:
            self.avg_speed = float(self.route.distance)/(float(self.duration.total_seconds())/60/60)
        # Save Route, just in case it needs something done
        if self.route:
            self.route.save()

        super(Exercise, self).save(*args, **kwargs)

    def parse(self):
        if self.sensor_file:
            task = parse_and_calculate.delay(self)
            return task
        return None


    def get_absolute_url(self):
        route_name = ''
        if self.route and self.route.name:
            route_name = slugify(self.route.name)
        return reverse('exercise', kwargs={ 'object_id': self.id }) + '/' + route_name

    def get_geojson_url(self):
        return reverse('exercise_geojson', kwargs={'object_id': self.id})

    def get_simplegpx_url(self):
        ''' Also defined here in addition to in Route because of how Mapper.js is initiated '''
        if self.route:
            return self.route.get_simplegpx_url()

    def icon(self):
        return self.exercise_type.icon()

    def is_smart_sampled(self):
        filename = self.sensor_file.name
        if filename.lower().endswith('.tcx'):
            exercise_details = self.get_details().all()[1:3]
            delta_t = (exercise_details[1].time - exercise_details[0].time).seconds
            if delta_t > 1:
                return True
        elif filename.lower().endswith('.fit'):
            if not self.avg_power: # Edges smart sample if no power meter
                return True
        return False

    class Meta:
        verbose_name = _("Exercise")
        verbose_name_plural = _("Exercises")
        ordering = ('-date','-time')
        #unique_together = ("date", "time", "user")

    def __unicode__(self):
        return u'%s, %s %s' %(self.get_name(), _('by'), self.user.get_profile().get_name())

    def get_name(self):
        name = _('Untitled')
        if self.route and self.route.name:
            name = self.route.name
            if name == '/dev/null': # TODO: Remove this old hack from db
                name = unicode(self.exercise_type)
        else:
            name = unicode(self.exercise_type)
        return name

    def delete(self, *args, **kwargs):
        ''' Also delete single serving route '''
        if self.route:
            if self.route.single_serving:
                if not self.route.exercise_set.count() > 1: # Do not delete single serving routes that have multiple exercises attachted
                    self.route.delete()
        super(Exercise, self).delete(*args, **kwargs)

    def get_intensityfactor(self):
        ''' Find IF for exercise '''
        userftp = self.user.get_profile().get_ftp(self.date)
        try:
            return round(float(self.normalized_power)/userftp, 3)
        except ZeroDivisionError:
            return 0

    def get_tss(self):
        ''' Estimating TSS
        http://home.trainingpeaks.com/articles/cycling/estimating-training-stress-score-(tss)-by-joe-friel.aspx '''
        userftp = self.user.get_profile().get_ftp(self.date)
        tss = int(round(float(self.duration.total_seconds() * self.normalized_power * self.get_intensityfactor() ) / ( userftp * 3600 ) * 100))
        return tss

    def get_ri(self):
        userftp = self.user.get_profile().get_ftp(self.date)
        # TODO write memoize function attr for self.userftp
        return float(self.xPower) / userftp

    def get_bikescore(self):
        ''' Find bikescore for exercise '''
        userftp = self.user.get_profile().get_ftp(self.date)
        if not self.duration:
            return
        if not self.xPower:
            return
        try:
            normalized_work = self.xPower * self.duration.seconds
            bikescore = normalized_work * self.get_ri()
            bikescore = bikescore / (3600 * userftp)
            bikescore = bikescore * 100
            return int(round(bikescore))
        except ZeroDivisionError:
            return None
        except TypeError:
            return None

    def get_full_start_time(self):
        ''' Used to get date and time '''

        start_time = datetime(self.date.year, self.date.month, self.date.day, self.time.hour, self.time.minute, self.time.second)
        return start_time

    @property
    def start_lon(self):
        if self.route and self.route.start_lon:
            return self.route.start_lon
        return 0.0

    @property
    def start_lat(self):
        if self.route and self.route.start_lat:
            return self.route.start_lat
        return 0.0

    @property
    def end_lat(self):
        if self.route and self.route.end_lat:
            return self.route.end_lat
        return 0.0

    @property
    def end_lon(self):
        if self.route and self.route.end_lon:
            return self.route.end_lon
        return 0.0

    def get_weight(self):
        ''' Find weight during exercise '''
        return self.user.get_profile().get_weight(self.date)

    def get_eq_weight(self):
        ''' Return weight of equipment '''
        eqweight = 10
        if self.equipment and self.equipment.get_weight() > 0:
            return self.equipment.get_weight()
        return eqweight




class ExercisePermission(models.Model):
    exercise = models.OneToOneField(Exercise, primary_key=True)
    speed = models.CharField(max_length=1, choices=permission_choices, default='A')
    power = models.CharField(max_length=1, choices=permission_choices, default='A')
    cadence = models.CharField(max_length=1, choices=permission_choices, default='A')
    hr = models.CharField(max_length=1, choices=permission_choices, default='A')

    def __unicode__(self):
        return u"%s (%s, %s, %s, %s)" % (self.exercise, self.speed, self.power, self.cadence, self.hr)

class ExerciseDetail(models.Model):

    exercise   = models.ForeignKey(Exercise)
    time       = models.DateTimeField()
    distance   = models.FloatField(blank=True, null=True)
    speed      = models.FloatField(blank=True, null=True)
    hr         = models.IntegerField(blank=True, null=True)
    altitude   = models.FloatField(blank=True, null=True)
    lat        = models.FloatField(blank=True, null=True)
    lon        = models.FloatField(blank=True, null=True)
    cadence    = models.IntegerField(blank=True, null=True)
    power      = models.IntegerField(blank=True, null=True)
    temp       = models.FloatField(blank=True, null=True)

    def get_relative_time(self):
        start_time = datetime(self.time.year, self.time.month, self.time.day, self.trip.time.hour, self.trip.time.minute, self.trip.time.second)
        return self.time - start_time

    class Meta:
        ordering = ('time',)


class BestPowerEffort(models.Model):
    exercise = models.ForeignKey(Exercise)
    pos = models.FloatField()
    length = models.FloatField()
    duration = models.IntegerField()
    power = models.IntegerField()
    ascent = models.IntegerField()
    descent = models.IntegerField()

    class Meta:
        ordering = ('duration',)

class HRZoneSummary(models.Model):
    exercise = models.ForeignKey(Exercise)
    zone = models.IntegerField()
    duration = models.IntegerField()

    class Meta:
        ordering = ('zone',)

class WZoneSummary(models.Model):
    exercise = models.ForeignKey(Exercise)
    zone = models.IntegerField()
    duration = models.IntegerField()

    class Meta:
        ordering = ('zone',)


class BestSpeedEffort(models.Model):
    exercise = models.ForeignKey(Exercise)
    pos = models.FloatField()
    length = models.FloatField()
    duration = models.IntegerField()
    speed = models.FloatField()
    ascent = models.IntegerField()
    descent = models.IntegerField()

    class Meta:
        ordering = ('duration',)

merge_choices = (
            ('M', _('Merge')),
            ('P', _('Prepend')),
            ('A', _('Append')),
                    )

class MergeSensorFile(models.Model):
    exercise = models.ForeignKey(Exercise)
    merge_strategy = models.CharField(max_length=1, choices=merge_choices, default='M', help_text=_('Merge strategy. Merge = Merge on top of current, Append = Append to end, Prepend = Insert before current'))
    sensor_file = models.FileField(_('Exercise file'), upload_to='sensor', storage=gpxstore, help_text=_('File from equipment from Garmin/Polar (.gpx, .tcx, .hrm, .gmd, .csv, .pwx, .xml, .fit)'))
    hr = models.BooleanField(blank=True, default=0)
    power = models.BooleanField(blank=True, default=0)
    cadence = models.BooleanField(blank=True, default=0)
    altitude = models.BooleanField(blank=True, default=0)
    position = models.BooleanField(blank=True, default=0)
    speed = models.BooleanField(blank=True, default=0)

    def save(self, *args, **kwargs):
        ''' Trigger merging on creation '''
        super(MergeSensorFile, self).save(*args, **kwargs)
        merge_sensordata.apply(self.exercise)

    def __unicode__(self):
        result = 'Merge type %s with types: ' % self.merge_strategy
        vals = []
        for val in ('hr', 'power', 'cadence', 'altitude', 'speed', 'position'):
            if getattr(self, val):
                vals.append(val)
        result += ','.join(vals)
        result += u', into %s' % self.exercise

        return result

class Interval(models.Model):
    ''' Interval / Lap model '''

    exercise = models.ForeignKey(Exercise)

    start_time = models.DateTimeField()
    start = models.FloatField(help_text=_('in km'), blank=True, null=True)
    duration = models.IntegerField()
    distance = models.FloatField(help_text=_('in km'), null=True, blank=True, default=0)
    ascent = models.IntegerField(blank=True, null=True) # m
    descent = models.IntegerField(blank=True, null=True) # m

    avg_temp = models.FloatField(blank=True, null=True)
    kcal = models.IntegerField(blank=True, null=True)

    start_lat = models.FloatField(null=True, blank=True, default=0.0)
    start_lon = models.FloatField(null=True, blank=True, default=0.0)
    end_lat = models.FloatField(null=True, blank=True, default=0.0)
    end_lon = models.FloatField(null=True, blank=True, default=0.0)

    avg_hr = models.IntegerField(blank=True, null=True, default=0)
    avg_speed = models.FloatField(blank=True, null=True) #kmt
    avg_cadence = models.IntegerField(blank=True, null=True) # rpm
    avg_power = models.IntegerField(blank=True, null=True) # W

    max_hr = models.IntegerField(blank=True, null=True) # bpm 
    max_speed = models.FloatField(blank=True, null=True) #kmt
    max_cadence = models.IntegerField(blank=True, null=True) # rpm
    max_power = models.IntegerField(blank=True, null=True) # W

    min_hr = models.IntegerField(blank=True, null=True) # bpm 
    min_speed = models.FloatField(blank=True, null=True) #kmt
    min_cadence = models.IntegerField(blank=True, null=True) # rpm
    min_power = models.IntegerField(blank=True, null=True) # W

    avg_pedaling_cadence = models.IntegerField(blank=True, null=True) # rpm

    def get_avg_power_per_kg(self):
        ''' Find weight during exercise and calculate W/kg'''
        userweight = self.exercise.get_weight()
        try:
            if self.avg_power:
                return self.avg_power/userweight
        except ZeroDivisionError:
            return 0

    def get_ftp_percentage(self, userftp=None):
        if not userftp:
            userftp = self.exercise.user.get_profile().get_ftp(self.exercise.date)
        if userftp:
            return self.avg_power*100/userftp

    class Meta:
        ordering = ('start_time',)

    def get_zone(self):
        ' Return coggan watt zone for interval if power is available, else return hr OLT zone '

        watt_p = self.get_ftp_percentage()
        if watt_p:
            return watt2zone(watt_p)
        elif self.avg_hr:
            max_hr = self.exercise.user.get_profile().max_hr
            if max_hr:
                hr_percent = float(self.avg_hr)*100/max_hr
                return hr2zone(hr_percent)
        return 0


    def save(self, *args, **kwargs):
        ''' Calculate extra values before save '''

        if not self.start:
            startd = self.exercise.exercisedetail_set.filter(time=self.start_time)
            if startd:
                if startd[0].distance:
                    self.start = startd[0].distance
                else:
                    self.start = 0

        super(Interval, self).save(*args, **kwargs)

    def get_relative_time_in_minutes(self):
        seconds = (self.start_time - self.exercise.get_full_start_time()).seconds
        if seconds:
            return seconds/60
        return 0

class Segment(models.Model):
    name = models.CharField(max_length=160, help_text=_("for example Alpe d'Huez"))
    distance = models.FloatField(help_text=_('in km'), default=0)
    description = models.TextField(_('Description'), help_text=_('Describe where it starts and ends and other noteworthy details'))
    segment_url = models.URLField(_('External URL'), blank=True, help_text=_('E.g. added info for segment in external URL'))
    gpx_file = models.FileField(upload_to='gpx', blank=True, storage=gpxstore)

    ascent = models.IntegerField(blank=True, null=True) # m
    descent = models.IntegerField(blank=True, null=True) # m
    max_altitude = models.IntegerField(blank=True, null=True) # m
    min_altitude = models.IntegerField(blank=True, null=True) # m

    grade = models.FloatField(blank=True,default=0,null=True,)
    category = models.IntegerField(blank=True,default=0, null=True)

    start_lat = models.FloatField(null=True, blank=True, default=0.0)
    start_lon = models.FloatField(null=True, blank=True, default=0.0)
    end_lat = models.FloatField(null=True, blank=True, default=0.0)
    end_lon = models.FloatField(null=True, blank=True, default=0.0)

    created = models.DateTimeField(editable=False,auto_now_add=True,null=True)
    tags = TagField()

    def get_simplegpx_url(self):
        ''' Also defined here in addition to in Route because of how Mapper.js is initiated '''
        url = None
        if self.gpx_file:
            filename = 'gpx/segment/%s.gpx' %self.id
            if gpxstore.exists(filename):
                url = filename
            else:
                url = self.gpx_file
        return url

    def get_png_url(self):
        if self.gpx_file:
            filename = 'svg/segment/%s.png' %self.id
            if gpxstore.exists(filename):
                return '%sturan/%s' %(settings.MEDIA_URL, filename)
        return '/empty.gif'

    def get_absolute_url(self):
        return reverse('segment', kwargs={ 'object_id': self.id }) + '/' + slugify(self.name)

    def get_geojson_url(self):
        return reverse('segment_geojson', kwargs={'object_id': self.id})

    def get_slopes(self):
        return self.segmentdetail_set.all().order_by('duration')

    def get_toplist(self):
        return User.objects.filter(exercise__segmentdetail__segment__exact=self.id).annotate(duration=Min('exercise__segmentdetail__duration')).order_by('duration')[:3]
        #return SegmentDetail.objects.filter(segment=self.id).values('exercise__user').annotate(duration=Min('duration')).order_by('duration')

    def get_latest(self):
        return SegmentDetail.objects.filter(segment=self.id).order_by('-exercise__date','-exercise__time')

    def get_avg_ascent(self):
        ''' Return average ascent '''
        res =  self.get_slopes().aggregate(avg=Avg('ascent'))
        if 'avg' in res:
            return int(round(res['avg']))
        return None

    def save(self, *args, **kwargs):
        ''' Calculate extra values before save '''

        # Save first to get id
        super(Segment, self).save(*args, **kwargs)
        # Create gpxtrack for this segment
        if not self.gpx_file:
            for slope in self.get_slopes():
                if slope.exercise.route and slope.exercise.route.gpx_file:
                    trip = slope.exercise
                    tripdetails = trip.get_details().all()
                    if filldistance(tripdetails):
                        i = 0
                        start, stop= 0, 0
                        for d in tripdetails:
                            if not start and d.distance >= slope.start*1000:
                                start = i
                            elif start:
                                if d.distance > (slope.start*1000+ slope.length):
                                    stop = i
                                    break
                            i += 1
                    tripdetails = tripdetails[start:stop]
                    g = GPXWriter(tripdetails)
                    if g.points: # don't write gpx if not lon/lat-trip
                        filename = 'gpx/segment/%s.gpx' %self.id
                        self.gpx_file.save(filename, ContentFile(g.xml), save=True)
                        break
        #gradobj = SegmentAltitudeGradient.objects.filter(segment=self.id).exists()
        #if not gradobj:
        SegmentAltitudeGradient.objects.filter(segment=self.id).delete()
        if True: # TODO somehow figure out a way to get the sanest result
            # No Gradient Found, try and generate
            for slope in self.get_slopes():
                trip = slope.exercise
                tripdetails = trip.get_details().all()
                i = 0
                start, stop = 0, 0
                for d in tripdetails:
                    if not start and d.distance >= slope.start*1000:
                        start = i
                    elif start:
                        if d.distance > (slope.start*1000+ slope.length):
                            stop = i
                            break
                    i += 1
                tripdetails = tripdetails[start:stop]
                lons = [d.lon for d in tripdetails]
                lats = [d.lat for d in tripdetails]
                distances, gradients, altitudes = getgradients(tripdetails)
                if distances:
                    d_offset = distances[0]
                    for i in xrange(0, len(tripdetails)):
                        sag = SegmentAltitudeGradient()
                        sag.segment_id = self.id
                        sag.xaxis = distances[i]-d_offset
                        sag.gradient = gradients[i]
                        sag.altitude = altitudes[i]
                        sag.lon = lons[i]
                        sag.lat = lats[i]
                        sag.save()
                    break # only break if we found exercise with distances

        # generate png if it doesn't exist (after save, it uses id for filename)
        if self.gpx_file:
            filename = 'svg/segment/%s.png' %self.id
            if not gpxstore.exists(filename):
                create_png_from_gpx.delay(self.gpx_file.path, filename)

        for attr in ('ascent', 'grade', 'length', 'start_lon', 'start_lat', 'end_lon', 'end_lat'):
            for slope in self.get_slopes():
                slopeattr = attr
                if attr == 'length': # omg
                    slopeattr = 'distance' # so silly
                if not getattr(self, slopeattr):
                    slopeval = getattr(slope, attr)
                    if slopeval:
                        if slopeattr == 'distance': # this design is so silly, why vary between m and km?
                            slopeval = slopeval/1000
                        setattr(self, slopeattr, slopeval)
        self.category = get_category(self.grade, self.distance*1000)

        super(Segment, self).save(*args, **kwargs)

    def __unicode__(self):
        return u'%s' % (self.name)


class Slope(models.Model):
    exercise = models.ForeignKey(Exercise)
    segment = models.ForeignKey(Segment, blank=True, null=True)
    start = models.FloatField(help_text=_('in km'), default=0)
    length = models.FloatField(help_text=_('in km'), default=0)
    ascent = models.IntegerField(help_text=_('in m'), default=0)
    grade = models.FloatField()
    duration = models.IntegerField()
    speed = models.FloatField()
    est_power = models.FloatField()
    act_power = models.FloatField(default=0)
    power_per_kg = models.FloatField()
    vam = models.IntegerField(default=0)
    category = models.IntegerField()
    avg_hr = models.IntegerField(default=0)

    start_lat = models.FloatField(blank=True, null=True, default=0.0)
    start_lon = models.FloatField(blank=True, null=True, default=0.0)
    end_lat = models.FloatField(blank=True, null=True, default=0.0)
    end_lon = models.FloatField(blank=True, null=True, default=0.0)

    comment = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        ''' Calculate extra values before save '''

        self.power_per_kg = self.get_avg_power_kg()
        self.vam = self.get_vam()
        self.category = self.get_category()

        super(Slope, self).save(*args, **kwargs)


    def get_vam(self):
        ''' Return Vertical Ascended Meters / Hour,
        but only if slope category is 3 or lower '''

        ret = 0
        if self.get_category() < 4:
            ret = int(round((float(self.ascent)/self.duration)*3600))
        return ret

    def get_category(self):
        return get_category(self.grade, self.length)

    def get_avg_power_kg(self):
        ''' Find weight during exercise and calculate W/kg'''
        userweight = self.exercise.user.get_profile().get_weight(self.exercise.date)
        try:
            if self.act_power:
                return self.act_power/userweight
            return self.est_power / userweight
        except ZeroDivisionError:
            return 0


    def __unicode__(self):
        return u'%s, %s, %s' % (self.exercise, round(self.grade), round(self.length))

    class Meta:
        ordering = ('-exercise__date',)

    def get_absolute_url(self):
        if self.segment:
            return self.segment.get_absolute_url()

class SegmentDetailManager(models.Manager):
    ''' Removes non-public segments from lists '''

    def get_query_set(self):
        return super(SegmentDetailManager, self).get_query_set().filter(public=1)

class SegmentDetail(models.Model):

    exercise = models.ForeignKey(Exercise)
    segment = models.ForeignKey(Segment, blank=True, null=True, help_text=_("Optionally add this selection to a shared public segment"))
    public = models.BooleanField(blank=True, default=1)
    start = models.FloatField(help_text=_('in km'), default=0)
    length = models.FloatField(help_text=_('in m'), default=0)
    ascent = models.IntegerField(help_text=_('in m'), default=0)
    grade = models.FloatField()
    duration = models.IntegerField()
    speed = models.FloatField()
    est_power = models.FloatField()
    act_power = models.FloatField(default=0)
    power_per_kg = models.FloatField()
    vam = models.IntegerField(default=0)
    avg_hr = models.IntegerField(default=0)

    start_lat = models.FloatField(blank=True, null=True, default=0.0)
    start_lon = models.FloatField(blank=True, null=True, default=0.0)
    end_lat = models.FloatField(blank=True, null=True, default=0.0)
    end_lon = models.FloatField(blank=True, null=True, default=0.0)

    comment = models.TextField(blank=True, null=True)

    objects = SegmentDetailManager()

    def get_absolute_url(self):
        if self.segment:
            return self.segment.get_absolute_url()
        else:
            return self.exercise.get_absolute_url()

    def save(self, *args, **kwargs):
        ''' Save parent also to populate shit '''

        super(SegmentDetail, self).save(*args, **kwargs)
        if self.segment:
            self.segment.save()

    def category(self):
        if self.segment:
            return self.segment.category


    def __unicode__(self):
        if self.segment:
            return unicode(self.segment)
        return u''

    def is_segmentdetail(self):
        return True

    class Meta:
        ordering = ('duration',)


    def end(self):
        ''' Helper so we do not have to calculate end in templates '''

        return self.start + self.length/1000



class CommonAltitudeGradient(models.Model):
    xaxis   = models.FloatField()
    altitude   = models.FloatField()
    gradient   = models.FloatField()

    class Meta:
        ordering = ('xaxis',)

class ExerciseAltitudeGradient(CommonAltitudeGradient):
    exercise   = models.ForeignKey(Exercise)

class SegmentAltitudeGradient(CommonAltitudeGradient):
    segment   = models.ForeignKey(Segment)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)

class Location(models.Model):
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    town = models.CharField(max_length=128, blank=True)
    county = models.CharField(max_length=128, blank=True)
    state = models.CharField(max_length=128, blank=True)
    country = models.CharField(max_length=128, blank=True)
    url = models.CharField(max_length=128, blank=True, unique=True)

    def __unicode__(self):
        return u'%s (%s, %s) %s' % (self.town, self.lat, self.lon, self.url)

    class Meta:
        verbose_name = _("Location")
        verbose_name_plural = _("Locations")

def find_close_locations(lon, lat):
    """ Find any locations that are deemed close to lon/lat"""
    return Location.objects.filter(lon__gt=lon-1).filter(lon__lt=lon+1).filter(lat__gt=lat-1).filter(lat__lt=lat+1)

def find_nearest_town(lon, lat):
    ''' Iterate saved locations and find nearest town '''

    distance = 99999999
    town = ''

    for loc in find_close_locations(lon, lat):
        this_distance = proj_distance(lat, lon, loc.lat, loc.lon)
        if this_distance < distance:
            town = loc.town
            distance = this_distance

    return town

# handle notification of new comments
from threadedcomments.models import ThreadedComment
def new_comment(sender, instance, **kwargs):
    if isinstance(instance.content_object, Exercise):
        exercise = instance.content_object
        if notification:
            notification.send([exercise.user], "exercise_comment",
                {"user": instance.user, "exercise": exercise, "comment": instance})
models.signals.post_save.connect(new_comment, sender=ThreadedComment)


def delete_segmentdetail(sender, instance, **kwargs):
    ''' Save parent, to generate new altitudegradient, etc '''
    instance.segment.save()
models.signals.post_delete.connect(delete_segmentdetail, sender=SegmentDetail)




def get_category(grade, length):
    ''' The categories are the same as in the Tour De France or other bike race
    What we do is take the grade of the climb and the distance and multiply them. So, for example, a 2
    kilometer climb at 4% grade = 8000, and 8000 to 16000 is a category 4 climb. 16 to 32 is a category
    3 etc.
    Our categorization is based on the official UCI but with some modification.
    '''
    grade = grade * length
    if grade < 8000:
        return 5
    elif grade < 16000:
        return 4
    elif grade < 32000:
        return 3
    elif grade < 64000:
        return 2
    elif grade < 128000:
        return 1
    else:
        return 0 # HC ?

class AutoTranslateField(models.CharField):
    __metaclass__ = models.SubfieldBase

    def to_python(self, value):
        return str(_(value))


class GetOrNoneManager(models.Manager):
    """Adds get_or_none method to objects
    """
    def get_or_none(self, **kwargs):
        try:
            return self.get(**kwargs)
        except self.model.DoesNotExist:
            return None

class Freq(models.Model):
    freq_choices = (
        ('H', _('Heart rate')),
        ('C', _('Cadence')),
        ('P', _('Power')),
        ('S', _('Speed')),
    )
    exercise     = models.ForeignKey(Exercise)
    json         = models.TextField()
    freq_type    = models.CharField(max_length=1, choices=freq_choices)

    objects = GetOrNoneManager()
