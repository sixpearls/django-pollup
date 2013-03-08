#!/usr/bin/env python
# -*- coding: utf-8 -*-
import django
from django.db import models
from django.core.exceptions import ValidationError
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



"""

class PollMetaClass(models.base.ModelBase):
    def __new__(cls, name, bases, attrs):
        bases_votebases = []
        if 'VoteBase' in attrs:
            #custom VoteBase class
            bases_votebases.append(attrs.pop('VoteBase'))
        else:
            #inherit VoteBase class from Poll parents
            for base in bases:
                if hasattr(base,'VoteBase'):
                    bases_votebases.append(base.VoteBase)

        new = super(PollMetaClass, cls).__new__(cls, name, bases, attrs)

        vote_base_name = '%sVoteBase' % name
        class VoteBaseClassInnerMeta:
            # Using type('Meta', ...) gives a dictproxy error during model creation
            abstract = True
        setattr(VoteBaseClassInnerMeta, 'app_label', new._meta.app_label)
        votebase_attrs = {'__module__':new.__module__,'Meta': VoteBaseClassInnerMeta}
        new_votebase = type(vote_base_name,tuple(bases_votebases),votebase_attrs)
        setattr(new,'VoteBase', new_votebase)

        return new

class PollBase(models.Model):
    __metaclass__ = PollMetaClass

    title = models.CharField(max_length=255,blank=True)
    slug = models.SlugField(verbose_name=_('Slug'), unique=True, max_length=100)
    description_or_question = models.TextField(blank=True)
    require_auth = models.BooleanField(default=False,)

    class Meta:
        abstract = True

    def __unicode__(self):
        return self.title

    def vote(self,voter,choice_object):
        pass

    @classmethod
    def _populate_poll_reverse_helpers(cls):
        cls._meta.poll_reverse_field_names = {'choices': [], 'votes': []}
        cls._meta.poll_reverse_models = {'choices': [], 'votes': []}
        for rel in cls._meta.get_all_related_objects():
            if type(rel.field)==models.ForeignKey:
                if issubclass(rel.field.model,ChoiceBase):
                    key = 'choices'
                elif issubclass(rel.field.model,cls.VoteBase):
                    key = 'votes'
                else:
                    key = None

                if key is not None:
                    cls._meta.poll_reverse_field_names[key].append(rel.get_accessor_name())
                    cls._meta.poll_reverse_models[key].append(rel.field.model)

    @classmethod
    def _check_poll_reverse_helpers(cls):
        if hasattr(cls._meta,'poll_reverse_field_names') and hasattr(cls._meta,'poll_reverse_models'):
            return
        else:
            cls._populate_poll_reverse_helpers()

    @classmethod
    def choices_models(cls):
        cls._check_poll_reverse_helpers()
        return cls._meta.poll_reverse_models['choices']

    @classmethod
    def votes_models(cls):
        cls._check_poll_reverse_helpers()
        return cls._meta.poll_reverse_models['votes']

    def choices(self):
        self._check_poll_reverse_helpers()
        choices = []
        for field_name in self._meta.poll_reverse_field_names['choices']:
            choices += list(getattr(self,field_name).all())
        return choices

    def choices_objects(self):
        self._check_poll_reverse_helpers()
        choices_objects = []
        for field_name in self._meta.poll_reverse_field_names['choices']:
            choices_objects += [ choice.content_object for choice in getattr(self,field_name).all() ]
        return choices_objects

    def votes(self):
        self._check_poll_reverse_helpers()
        votes = []
        for field_name in self._meta.poll_reverse_field_names['votes']:
            votes += list(getattr(self,field_name).all())
        return votes

    @property
    def winner(self):
        # return first place choice
        return

    @property
    def loser(self):
        # return last place choice
        return

    class VoteBase(models.Model):
        time_stamp = models.DateTimeField(auto_now_add=True)

        class Meta:
            abstract = True

        def __unicode__(self):
            return u"Vote for choice: %(choice)s" % {'choice': self.choice}

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

class ScheduledPollMixin(models.Model):
    voting_opens_on = models.DateTimeField(default=datetime.now(), null=True, blank=True)
    voting_closes_on = models.DateTimeField(default=datetime.now(), null=True, blank=True)

    class Meta:
        abstract = True

class OneVotePerUserMixin(models.Model):
    one_vote_per_ip = models.BooleanField(default=True,)
    one_vote_per_user = models.BooleanField(default=True,)
    # if both IP and user, only one vote per user and one vote per ANON IP

    class Meta:
        abstract = True

    class VoteBase(models.Model):
        voter_ip = models.IPAddressField(blank=True,default='')
        if django.VERSION < (1, 2):
            voter = models.ForeignKey(UserModel,related_name="%(class)s_votes", blank=True,null=True)
        else:
            voter = models.ForeignKey(UserModel,related_name="%(app_label)s_%(class)s_votes",blank=True,null=True)
        
        class Meta:
            abstract = True

        def validate_unique(self,*args,**kwargs):
            lookup_kwargs = {'poll': self.poll,}
            do_check = False

            if self.poll.one_vote_per_user and self.voter is not None:
                lookup_kwargs['voter']=self.voter
                do_check |= True
            elif self.poll.one_vote_per_ip:
                lookup_kwargs['voter_ip']=self.voter_ip
                do_check |= True

            if do_check:
                qs = self._default_manager.filter(**lookup_kwargs)
                if not self._state.adding and self.pk is not None:
                    qs.exclude(pk=self.pk)
                if qs.exists():
                    raise ValidationError(_(u"%s with this Voter or Voter IP already exist" % self.__name__))

            super(OneVotePerUserMixin.VoteBase,self).validate_unique(*args,**kwargs)

class Poll(PollBase,ScheduledPollMixin,OneVotePerUserMixin):    
    class Meta:
        verbose_name = _("Poll")
        verbose_name_plural = _("Polls")

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
            if django.VERSION < (1, 2):
                attrs['poll'] = models.ForeignKey(new.poll_model(),related_name="%(class)s_votes")
            else:
                attrs['poll'] = models.ForeignKey(new.poll_model(),related_name="%(app_label)s_%(class)s_votes")
            attrs['choice'] = models.ForeignKey(new,related_name="votes") # only one vote class / choice class

            VoteClass = type(vote_class_name, (new.poll_model().VoteBase,), attrs)
            setattr(sys.modules[new.__module__],vote_class_name,VoteClass)

        return new

class ChoiceBase(models.Model):
    __metaclass__ = ChoiceMetaClass

    def __unicode__(self):
        return ugettext("%(choice)s in poll: %(poll)s") % {
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