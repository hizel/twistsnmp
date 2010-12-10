from django.db import models
from django.contrib import admin


class Host(models.Model):
    ip = models.IPAddressField()
    port = models.PositiveIntegerField(default=161)
    version = models.PositiveIntegerField(default=2)
    name = models.CharField(max_length=150, unique=True, db_index=True)
    rcomm = models.CharField(max_length=50)
    wcomm = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default = True)
    def __unicode__(self):
        return '%s[%s]' % (self.name,self.ip)

class Job(models.Model):
    host = models.ForeignKey(Host)
    name = models.CharField(max_length=150, db_index=True)
    plugin = models.CharField(max_length=150)
    freq = models.PositiveIntegerField(default=60)
    min = models.FloatField(blank=True)
    max = models.FloatField(blank=True)
    active = models.BooleanField(default = True)
    def __unicode__(self):
        return '%s - %s' % (self.host, self.name)

class JobOption(models.Model):
    job = models.ForeignKey(Job)
    name = models.CharField(max_length=50)
    value = models.CharField(max_length=50)

class HostAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip', 'port', 'version', 'rcomm', 'wcomm',
    'active')

class JobAdmin(admin.ModelAdmin):
    list_display = ('host', 'name', 'plugin', 'freq', 'min', 'max', 'active')

class JobOptionAdmin(admin.ModelAdmin):
    list_display = ('job', 'name', 'value')


admin.site.register(Host, HostAdmin)
admin.site.register(Job, JobAdmin)
admin.site.register(JobOption, JobOptionAdmin)
