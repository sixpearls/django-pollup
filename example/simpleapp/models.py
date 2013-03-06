from django.db import models
from pollup.models import PollBase, ChoiceBase
from pollup.managers import PollableManager

class CustomPoll(PollBase):
    pass

class CustomChoice(ChoiceBase):
    poll = models.ForeignKey(CustomPoll, related_name="choices")
    content_object = models.ForeignKey('SimpleModel', related_name="choices")

class SimpleModel(models.Model):
    """
    (SimpleModel description)
    """
    
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    polls = PollableManager()

    
    def __unicode__(self):
        return self.name
    
    @models.permalink
    def get_absolute_url(self):
        return ('simplemodel_detail_view_name', [str(self.id)])
    
