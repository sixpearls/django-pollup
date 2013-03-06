from django.contrib.contenttypes.generic import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields.related import ManyToManyRel, ManyToManyField, RelatedField, add_lazy_relation
from django.db.models.related import RelatedObject
from django.utils.text import capfirst
from django.utils.translation import ugettext_lazy as _

from django import forms

from pollup.models import PollChoice, GenericChoiceBase

try:
    all
except NameError:
    # 2.4 compat
    try:
        from django.utils.itercompat import all
    except ImportError:
        # 1.1.X compat
        def all(iterable):
            for item in iterable:
                if not item:
                    return False
            return True

from django.utils.functional import wraps
def require_instance_manager(func):
    @wraps(func)
    def inner(self, *args, **kwargs):
        if self.instance is None:
            raise TypeError("Can't call %s with a non-instance manager" % func.__name__)
        return func(self, *args, **kwargs)
    return inner

class PollableRel(ManyToManyRel):
    def __init__(self,related_name=None):
        self.related_name = related_name #Why Not?
        self.limit_choices_to = {}
        self.symmetrical = True
        self.multiple = True
        self.through = None


class PollableManager(RelatedField):
    def __init__(self, verbose_name=_("Polls"),
        help_text=_("The Polls"), through=None, related_name=None, blank=False):
        self.through = through or PollChoice
        self.rel = PollableRel(related_name=related_name)
        self.verbose_name = verbose_name
        self.help_text = help_text
        self.blank = blank
        self.editable = True
        self.unique = False
        self.creates_table = False
        self.db_column = None
        self.choices = None
        self.serialize = False
        self.null = True
        self.creation_counter = models.Field.creation_counter
        models.Field.creation_counter += 1

    def __get__(self, instance, model):
        if instance is not None and instance.pk is None:
            raise ValueError("%s objects need to have a primary key value "
                "before you can access their polls." % model.__name__)
        manager = _PollableManager(
            through=self.through, model=model, instance=instance
        )
        return manager

    def contribute_to_class(self, cls, name):
        self.name = self.column = name
        self.model = cls
        cls._meta.add_field(self)
        setattr(cls, name, self)
        if not cls._meta.abstract:
            if isinstance(self.through, basestring):
                def resolve_related_class(field, model, cls):
                    self.through = model
                    self.post_through_setup(cls)
                add_lazy_relation(
                    cls, self, self.through, resolve_related_class
                )
            else:
                self.post_through_setup(cls)

    def post_through_setup(self, cls):
        self.use_gfk = (
            self.through is None or issubclass(self.through, GenericChoiceBase)
        )
        self.rel.to = self.through._meta.get_field("poll").rel.to
        if self.use_gfk:
            poll_choices = GenericRelation(self.through)
            poll_choices.contribute_to_class(cls, "poll_choices")

    def save_form_data(self, instance, value):
        getattr(instance, self.name).set(*value)

    def value_from_object(self, instance):
        if instance.pk:
            return self.through.objects.filter(**self.through.lookup_kwargs(instance))
        return self.through.objects.none()

    def related_query_name(self):
        return self.model._meta.module_name

    def m2m_reverse_name(self):
        return self.through._meta.get_field_by_name("poll")[0].column

    def m2m_target_field_name(self):
        return self.model._meta.pk.name

    def m2m_reverse_target_field_name(self):
        return self.rel.to._meta.pk.name

    def m2m_column_name(self):
        if self.use_gfk:
            return self.through._meta.virtual_fields[0].fk_field
        return self.through._meta.get_field('content_object').column

    def db_type(self, connection=None):
        return None

    def m2m_db_table(self):
        return self.through._meta.db_table

    def formfield(self, **kwargs):
        return None

    def extra_filters(self, pieces, pos, negate):
        if negate or not self.use_gfk:
            return []
        prefix = "__".join(["poll_choices"] + pieces[:pos-2])
        cts = map(ContentType.objects.get_for_model, _get_subclasses(self.model))
        if len(cts) == 1:
            return [("%s__content_type" % prefix, cts[0])]
        return [("%s__content_type__in" % prefix, cts)]

class _PollableManager(models.Manager):
    def __init__(self, through, model, instance):
        self.through = through
        self.model = model
        self.instance = instance

    def get_query_set(self):
        return self.through.choices_for(self.model, self.instance)

    def _lookup_kwargs(self):
        return self.through.lookup_kwargs(self.instance)

    @require_instance_manager
    def add(self, *polls):
        for poll in polls:
            self.through.objects.get_or_create(poll=poll, **self._lookup_kwargs())

    @require_instance_manager
    def set(self, *polls):
        self.clear()
        self.add(*polls)

    @require_instance_manager
    def remove(self, *polls):
        self.through.objects.filter(**self._lookup_kwargs()).filter(
            poll__in=list(polls)).delete()

    @require_instance_manager
    def clear(self):
        self.through.objects.filter(**self._lookup_kwargs()).delete()


def _get_subclasses(model):
    subclasses = [model]
    for f in model._meta.get_all_field_names():
        field = model._meta.get_field_by_name(f)[0]
        if (isinstance(field, RelatedObject) and
            getattr(field.field.rel, "parent_link", None)):
            subclasses.extend(_get_subclasses(field.model))
    return subclasses