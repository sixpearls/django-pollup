#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.contrib import admin
from pollup.models import Poll, PollChoice


class PollChoiceInline(admin.StackedInline):
    model = PollChoice

class PollAdmin(admin.ModelAdmin):
    list_display = ["title"]
    inlines = [
        PollChoiceInline
    ]


admin.site.register(Poll, PollAdmin)