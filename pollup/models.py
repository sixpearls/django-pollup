#!/usr/bin/env python
# -*- coding: utf-8 -*-
import django
from django.db import models
from django.conf import settings as site_settings
from django.utils.translation import ugettext, ugettext_lazy as _

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.generic import GenericForeignKey

from pollup import settings
from datetime import datetime

import sys

if django.VERSION < (1, 5):
    from django.contrib.auth.models import User as UserModel
else:
    UserModel = site_settings.AUTH_USER_MODEL

"""
polls should be just like tags. Add a Poll field to the model you
want to be able to vote on.

class MyModel(models.Model):
    polls = PollableManager()

MyModel.polls.all()
MyModel.polls.won()
MyModel.polls.lost()

customize the PollModel:

class MyModel(models.Model):
    polls = PollableManager(through=MyThroughModel)


How to vote?

PollInstance.vote(voter="",choice="")
MyModel.polls.vote(poll=PollInstance,voter="")

"""
class PollBase(models.Model):

    title = models.CharField(max_length=255,blank=True)
    slug = models.SlugField(verbose_name=_('Slug'), unique=True, max_length=100)
    description_or_question = models.TextField(blank=True)

    class Meta:
        abstract = True

    def __unicode__(self):
        return self.title

    def vote(self,voter,choice_object):
        pass

    @classmethod
    def choice_field_names(cls):
        choice_field_names = []
        for rel in cls._meta.get_all_related_objects():
            if issubclass(rel.field.model,ChoiceBase) and type(rel.field)==models.ForeignKey:
                choice_field_names.append(rel.get_accessor_name())
        return choice_field_names

    def choices(self):
        choices = []
        for field_name in self.__class__.choice_field_names():
            choices += list(getattr(self,field_name).all())
        return choices

    def choice_objects(self):
        choice_objects = []
        for field_name in self.__class__.choice_field_names():
            choice_objects += [ choice.content_object for choice in getattr(self,field_name).all() ]
        return choice_objects

    @property
    def winner(self):
        # return first place choice
        return

    @property
    def loser(self):
        # return last place choice
        return

class ScheduledPollMixin(models.Model):
    voting_opens_on = models.DateTimeField(default=datetime.now(), null=True, blank=True)
    voting_closes_on = models.DateTimeField(default=datetime.now(), null=True, blank=True)

    class Meta:
        abstract = True

class OneVotePerUserMixin(models.Model):
    log_vote_by_ip = models.BooleanField(default=False,)
    log_vote_by_user = models.BooleanField(default=False,)
    # if both IP and user, only one vote per user and one vote per ANON IP

    class Meta:
        abstract = True


class Poll(PollBase,ScheduledPollMixin,OneVotePerUserMixin):    
    class Meta:
        verbose_name = _("Poll")
        verbose_name_plural = _("Polls")

class VoteBase(models.Model):
    voter_ip = models.IPAddressField(blank=True)
    if django.VERSION < (1, 2):
        voter = models.ForeignKey(UserModel,related_name="%(class)s_votes", blank=True,null=True)
    else:
        voter = models.ForeignKey(UserModel,related_name="%(app_label)s_%(class)s_votes",blank=True,null=True)
        
    time_stamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    @classmethod
    def poll_model(cls):
        return cls._meta.get_field_by_name("poll")[0].rel.to

    @classmethod
    def poll_relname(cls):
        return cls._meta.get_field_by_name('poll')[0].rel.related_name

    @classmethod
    def choice_model(cls):
        return cls._meta.get_field_by_name("choice")[0].rel.to

    @classmethod
    def choice_relname(cls):
        return cls._meta.get_field_by_name('choice')[0].rel.related_name

class ChoiceMetaClass(models.base.ModelBase):
    def __new__(cls, name, bases, attrs):
        new = super(ChoiceMetaClass, cls).__new__(cls, name, bases, attrs)

        if not new._meta.abstract:
            vote_class_name = "%sVote" % name
            class VoteClassInnerMeta:
                # Using type('Meta', ...) gives a dictproxy error during model creation
                pass
            setattr(VoteClassInnerMeta, 'app_label', new._meta.app_label)

            attrs = {'__module__': new.__module__, 'Meta': VoteClassInnerMeta}
            attrs['poll'] = models.ForeignKey(new.poll_model())
            attrs['choice'] = models.ForeignKey(new)

            VoteClass = type(vote_class_name, (VoteBase,), attrs)
            setattr(sys.modules[new.__module__],vote_class_name,VoteClass)

        return new

class ChoiceBase(models.Model):
    __metaclass__ = ChoiceMetaClass

    def __unicode__(self):
        return ugettext("%(choice)s choice for %(poll)s") % {
            "choice": self.content_object,
            "poll": self.poll
        }

    class Meta:
        abstract = True

    @classmethod
    def poll_model(cls):
        return cls._meta.get_field_by_name("poll")[0].rel.to

    @classmethod
    def poll_relname(cls):
        return cls._meta.get_field_by_name('poll')[0].rel.related_name

    @classmethod
    def lookup_kwargs(cls, instance):
        return {
            'content_object': instance
        }

    @classmethod
    def bulk_lookup_kwargs(cls, instances):
        return {
            "content_object__in": instances,
        }

    @classmethod
    def choices_for(cls, model, instance=None):
        if instance is not None:
            return cls.poll_model().objects.filter(**{
                '%s__content_object' % cls.poll_relname(): instance
            })
        return cls.poll_model().objects.filter(**{
            '%s__content_object__isnull' % cls.poll_relname(): False
        }).distinct()

class PollChoiceBase(ChoiceBase):
    if django.VERSION < (1, 2):
        poll = models.ForeignKey(Poll, related_name="%(class)s_choices")
    else:
        poll = models.ForeignKey(Poll, related_name="%(app_label)s_%(class)s_choices")

    class Meta:
        abstract = True

    @classmethod
    def choices_for(cls, model, instance=None):
        if instance is not None:
            return cls.poll_model().objects.filter(**{
                '%s__content_object' % cls.poll_relname(): instance
            })
        return cls.poll_model().objects.filter(**{
            '%s__content_object__isnull' % cls.poll_relname(): False
        }).distinct()

class GenericChoiceBase(ChoiceBase):
    object_id = models.IntegerField(verbose_name=_('Object id'), db_index=True)
    if django.VERSION < (1, 2):
        content_type = models.ForeignKey(
            ContentType,
            verbose_name=_('Content type'),
            related_name="%(class)s_choice_items"
        )
    else:
        content_type = models.ForeignKey(
            ContentType,
            verbose_name=_('Content type'),
            related_name="%(app_label)s_%(class)s_choice_items"
        )
    content_object = GenericForeignKey()

    class Meta:
        abstract=True

    @classmethod
    def lookup_kwargs(cls, instance):
        return {
            'object_id': instance.pk,
            'content_type': ContentType.objects.get_for_model(instance)
        }

    @classmethod
    def bulk_lookup_kwargs(cls, instances):
        # TODO: instances[0], can we assume there are instances.... 
        return {
            "object_id__in": [instance.pk for instance in instances],
            "content_type": ContentType.objects.get_for_model(instances[0]),
        }

    @classmethod
    def choices_for(cls, model, instance=None):
        ct = ContentType.objects.get_for_model(model)
        kwargs = {
            "%s__content_type" % cls.poll_relname(): ct
        }
        if instance is not None:
            kwargs["%s__object_id" % cls.poll_relname()] = instance.pk
        return cls.poll_model().objects.filter(**kwargs).distinct()

class PollChoice(GenericChoiceBase,PollChoiceBase):
    class Meta:
        verbose_name = _("Poll Choice")
        verbose_name_plural = _("Poll Choices")