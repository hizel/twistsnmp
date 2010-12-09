from django.db import models


class Host(models.Model):
    ip = models.IPAddressField()
    port = models.PositiveIntegerField(default=161)
    version = models.PositiveIntegerField(default=2)
    name = models.CharField(max_length=150, unique=True, db_index=True)
    rcomm = models.CharField(max_length=50)
    wcomm = models.CharField(max_length=50, blank=True)

class Job(models.Model):
    host = models.ForeignKey(Host)
    name = models.CharField(max_length=150, db_index=True)
    plugin = models.CharField(max_length=150)
    freq = models.PositiveIntegerField(default=60)
    min = models.FloatField(blank=True)
    max = models.FloatField(blank=True)
