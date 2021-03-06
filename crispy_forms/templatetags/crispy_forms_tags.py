# -*- coding: utf-8 -*-
from django.conf import settings
from django.forms.formsets import BaseFormSet
from django.template import Context
from django.template.loader import get_template
from django import template

from crispy_forms.helper import FormHelper

register = template.Library()
# We import the filters, so they are available when doing load crispy_forms_tags
from crispy_forms_filters import *

TEMPLATE_PACK = getattr(settings, 'CRISPY_TEMPLATE_PACK', 'bootstrap')


class ForLoopSimulator(object):
    """
    Simulates a forloop tag, precisely::

        {% for form in formset.forms %}

    If `{% crispy %}` is rendering a formset with a helper, We inject a `ForLoopSimulator` object
    in the context as `forloop` so that formset forms can do things like::

        Fieldset("Item {{ forloop.counter }}", [...])
        HTML("{% if forloop.first %}First form text{% endif %}"
    """
    def __init__(self, formset):
        self.len_values = len(formset.forms)

        # Shortcuts for current loop iteration number.
        self.counter = 1
        self.counter0 = 0
        # Reverse counter iteration numbers.
        self.revcounter = self.len_values
        self.revcounter0 = self.len_values - 1
        # Boolean values designating first and last times through loop.
        self.first = True
        self.last = (0 == self.len_values - 1)

    def iterate(self):
        """
        Updates values as if we had iterated over the for
        """
        self.counter += 1
        self.counter0 += 1
        self.revcounter -= 1
        self.revcounter0 -= 1
        self.first = False
        self.last = (self.revcounter0 == self.len_values - 1)


class BasicNode(template.Node):
    """
    Basic Node object that we can rely on for Node objects in normal
    template tags. I created this because most of the tags we'll be using
    will need both the form object and the helper string. This handles
    both the form object and parses out the helper string into attributes
    that templates can easily handle.
    """
    def __init__(self, form, helper):
        self.form = form
        if helper is not None:
            self.helper = helper
        else:
            self.helper = None

    def get_render(self, context):
        """
        Returns a `Context` object with all the necesarry stuff for rendering the form

        :param context: `django.template.Context` variable holding the context for the node

        `self.form` and `self.helper` are resolved into real Python objects resolving them
        from the `context`. The `actual_form` can be a form or a formset. If it's a formset
        `is_formset` is set to True. If the helper has a layout we use it, for rendering the
        form or the formset's forms.
        """
        # Nodes are not thread safe in multithreaded environments
        # https://docs.djangoproject.com/en/dev/howto/custom-template-tags/#thread-safety-considerations
        if self not in context.render_context:
            context.render_context[self] = (
                template.Variable(self.form),
                template.Variable(self.helper) if self.helper else None
            )
        form, helper = context.render_context[self]

        actual_form = form.resolve(context)
        if self.helper is not None:
            helper = helper.resolve(context)
        else:
            # If the user names the helper within the form `helper` (standard), we use it
            # This allows us to have simplified tag syntax: {% crispy form %}
            helper = FormHelper() if not hasattr(actual_form, 'helper') else actual_form.helper

        # We get the response dictionary
        is_formset = isinstance(actual_form, BaseFormSet)
        response_dict = self.get_response_dict(helper, context, is_formset)
        node_context = context.__copy__()
        node_context.update(response_dict)

        # If we have a helper's layout we use it, for the form or the formset's forms
        if helper and helper.layout:
            if not is_formset:
                actual_form.form_html = helper.render_layout(actual_form, node_context)
            else:
                forloop = ForLoopSimulator(actual_form)
                for form in actual_form.forms:
                    node_context.update({'forloop': forloop})
                    form.form_html = helper.render_layout(form, node_context)
                    forloop.iterate()

        if is_formset:
            response_dict.update({'formset': actual_form})
        else:
            response_dict.update({'form': actual_form})

        return Context(response_dict)

    def get_response_dict(self, helper, context, is_formset):
        """
        Returns a dictionary with all the parameters necessary to render the form/formset in a template.

        :param attrs: Dictionary with the helper's attributes used for rendering the form/formset
        :param context: `django.template.Context` for the node
        :param is_formset: Boolean value. If set to True, indicates we are working with a formset.
        """
        if not isinstance(helper, FormHelper):
            raise TypeError('helper object provided to {% crispy %} tag must be a crispy.helper.FormHelper object.')

        attrs = helper.get_attributes()
        form_type = "form"
        if is_formset:
            form_type = "formset"

        # We take form/formset parameters from attrs if they are set, otherwise we use defaults
        response_dict = {
            '%s_action' % form_type: attrs['attrs'].get("action", ''),
            '%s_method' % form_type: attrs.get("form_method", 'post'),
            '%s_tag' % form_type: attrs.get("form_tag", True),
            '%s_class' % form_type: attrs['attrs'].get("class", ''),
            '%s_id' % form_type: attrs['attrs'].get("id", ""),
            '%s_style' % form_type: attrs.get("form_style", None),
            'form_error_title': attrs.get("form_error_title", None),
            'formset_error_title': attrs.get("formset_error_title", None),
            'form_show_errors': attrs.get("form_show_errors", True),
            'help_text_inline': attrs.get("help_text_inline", False),
            'html5_required': attrs.get("html5_required", False),
            'inputs': attrs.get('inputs', []),
            'is_formset': is_formset,
            '%s_attrs' % form_type: attrs.get('attrs', ''),
            'flat_attrs': attrs.get('flat_attrs', ''),
        }

        # Handles custom attributes added to helpers
        for attribute_name, value in attrs.items():
            if attribute_name not in response_dict:
                response_dict[attribute_name] = value

        if context.has_key('csrf_token'):
            response_dict['csrf_token'] = context['csrf_token']

        return response_dict


whole_uni_formset_template = get_template('%s/whole_uni_formset.html' % TEMPLATE_PACK)
whole_uni_form_template = get_template('%s/whole_uni_form.html' % TEMPLATE_PACK)

class CrispyFormNode(BasicNode):
    def render(self, context):
        c = self.get_render(context)

        if c['is_formset']:
            if settings.DEBUG:
                template = get_template('%s/whole_uni_formset.html' % TEMPLATE_PACK)
            else:
                template = whole_uni_formset_template
        else:
            if settings.DEBUG:
                template = get_template('%s/whole_uni_form.html' % TEMPLATE_PACK)
            else:
                template = whole_uni_form_template

        return template.render(c)


# {% crispy %} tag
@register.tag(name="uni_form")
@register.tag(name="crispy")
def do_uni_form(parser, token):
    """
    You need to pass in at least the form/formset object, and can also pass in the
    optional `crispy_forms.helpers.FormHelper` object.

    helper (optional): A `uni_form.helper.FormHelper` object.

    Usage::

        {% include crispy_tags %}
        {% crispy form form.helper %}

    If the `FormHelper` attribute is named `helper` you can simply do::

        {% crispy form %}
    """
    token = token.split_contents()
    form = token.pop(1)

    try:
        helper = token.pop(1)
    except IndexError:
        helper = None

    return CrispyFormNode(form, helper)
