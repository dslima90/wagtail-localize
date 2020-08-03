from django import forms

from django.contrib import messages
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy as __
from wagtail.admin.views.pages import get_valid_next_url_from_request
from wagtail.core.models import Page, Locale, TranslatableMixin
from wagtail.snippets.views.snippets import get_snippet_model_from_url_params

from wagtail_localize.models import Translation, TranslationSource


class SubmitTranslationForm(forms.Form):
    update_locales = forms.ModelMultipleChoiceField(
        label=__("Update existing translations"),
        queryset=Locale.objects.none(), widget=forms.CheckboxSelectMultiple, required=False
    )
    update_subtree = forms.BooleanField(label=__("Include subtree"), required=False, help_text=__("Existing pages will be updated, no new pages will be created."))

    create_locales = forms.ModelMultipleChoiceField(
        label=__("Create new translations"),
        queryset=Locale.objects.none(), widget=forms.CheckboxSelectMultiple, required=False
    )
    create_subtree = forms.BooleanField(label=__("Include subtree"), required=False, help_text=__("All child pages will be created."))

    def __init__(self, instance, *args, **kwargs):
        super().__init__(*args, **kwargs)

        locales = Locale.objects.exclude(id=instance.locale_id)
        active_locales_q = Q(id__in=Translation.objects.filter(object_id=instance.translation_key, enabled=True).values_list('target_locale_id', flat=True))
        self.fields["update_locales"].queryset = locales.filter(active_locales_q)
        self.fields["create_locales"].queryset = locales.exclude(active_locales_q)

        if isinstance(instance, Page):
            has_descendants = instance.get_descendants().exists()
        else:
            has_descendants = False

        if not has_descendants:
            self.fields["update_subtree"].widget = forms.HiddenInput()
            self.fields["create_subtree"].widget = forms.HiddenInput()

        if not self.fields["update_locales"].queryset.exists():
            self.fields["update_locales"].widget = forms.HiddenInput()
            self.fields["update_subtree"].widget = forms.HiddenInput()

        if not self.fields["create_locales"].queryset.exists():
            self.fields["create_locales"].widget = forms.HiddenInput()
            self.fields["create_subtree"].widget = forms.HiddenInput()


class TranslationCreator:
    """
    A class that provides a create_translations method.

    Call create_translations for each object you want to translate and this will submit
    that object and any dependencies as well.

    This class will track the objects that have already submitted so an object doesn't
    get submitted twice.
    """
    def __init__(self, user, update_locales, create_locales):
        self.user = user
        self.update_locales = update_locales
        self.create_locales = create_locales
        self.updated_objects = set()
        self.created_objects = set()

    def update_translations(self, instance, include_related_objects=True):
        if not self.update_locales:
            return

        if isinstance(instance, Page):
            instance = instance.specific

        if instance.translation_key in self.updated_objects:
            return
        self.updated_objects.add(instance.translation_key)

        source, created = TranslationSource.from_instance(instance)

        if created:
            source.extract_segments()

        # Add related objects
        # Must be before translation records or those translation records won't be able to create
        # the objects because the dependencies haven't been created
        if include_related_objects:
            for related_object_segment in source.relatedobjectsegment_set.all():
                related_instance = related_object_segment.object.get_instance(instance.locale)

                # Limit to one level of related objects, since this could potentially pull in a lot of stuff
                self.update_translations(related_instance, include_related_objects=False)

        # Set up translation records
        for target_locale in self.update_locales:
            # Update translation if it exists
            try:
                translation = Translation.objects.get(object=source.object, target_locale=target_locale)

                if translation.source != source:
                    translation.source = source
                    translation.source_last_updated_at = timezone.now()
                    translation.save(update_fields=['source', 'source_last_updated_at'])
                    translation.save_target(user=self.user)

            except Translation.DoesNotExist:
                continue

    def create_translations(self, instance, include_related_objects=True):
        if not self.create_locales:
            return

        if isinstance(instance, Page):
            instance = instance.specific

        if instance.translation_key in self.created_objects:
            return
        self.created_objects.add(instance.translation_key)

        source, created = TranslationSource.from_instance(instance)

        if created:
            source.extract_segments()

        # Add related objects
        # Must be before translation records or those translation records won't be able to create
        # the objects because the dependencies haven't been created
        if include_related_objects:
            for related_object_segment in source.relatedobjectsegment_set.all():
                related_instance = related_object_segment.object.get_instance(instance.locale)

                # Limit to one level of related objects, since this could potentially pull in a lot of stuff
                self.create_translations(related_instance, include_related_objects=False)

        # Set up translation records
        for target_locale in self.create_locales:
            # Create or update translation
            translation, created = Translation.objects.get_or_create(object=source.object, target_locale=target_locale, defaults={'source': source})

            if created or translation.source != source:
                translation.source = source
                translation.source_last_updated_at = timezone.now()
                translation.save(update_fields=['source', 'source_last_updated_at'])
                translation.save_target(user=self.user)


def submit_page_translation(request, page_id):
    if not request.user.has_perms(['wagtail_localize.submit_translation']):
        raise PermissionDenied

    page = get_object_or_404(Page, id=page_id).specific
    next_url = get_valid_next_url_from_request(request)

    if request.method == "POST":
        form = SubmitTranslationForm(page, request.POST)

        if form.is_valid():
            with transaction.atomic():
                translator = TranslationCreator(request.user, form.cleaned_data["update_locales"], form.cleaned_data["create_locales"])
                translator.create_translations(page)
                translator.update_translations(page)

                # Now add the sub tree
                if form.cleaned_data["update_subtree"] or form.cleaned_data["create_subtree"]:
                    def _walk(current_page):
                        for child_page in current_page.get_children():
                            if form.cleaned_data["update_subtree"] :
                                translator.update_translations(child_page)

                            if form.cleaned_data["create_subtree"]:
                                translator.create_translations(child_page)

                            if child_page.numchild:
                                _walk(child_page)

                    _walk(page)

                # TODO: Button that links to page in translations report when we have it
                messages.success(
                    request, _("The page '{}' was successfully submitted for translation").format(page.title)
                )

                if next_url:
                    return redirect(next_url)
                else:
                    return redirect("wagtailadmin_explore", page.get_parent().id)
    else:
        form = SubmitTranslationForm(page)

    return render(
        request,
        "wagtail_localize/admin/submit_page_translation.html",
        {"page": page, "form": form, "next_url": next_url},
    )


def submit_snippet_translation(request, app_label, model_name, pk):
    if not request.user.has_perms(['wagtail_localize.submit_translation']):
        raise PermissionDenied

    model = get_snippet_model_from_url_params(app_label, model_name)

    if not issubclass(model, TranslatableMixin):
        raise Http404

    instance = get_object_or_404(model, pk=unquote(pk))
    next_url = get_valid_next_url_from_request(request)

    if request.method == "POST":
        form = SubmitTranslationForm(instance, request.POST)

        if form.is_valid():
            with transaction.atomic():
                translator = TranslationCreator(request.user, form.cleaned_data["update_locales"], form.cleaned_data["create_locales"])
                translator.create_translations(instance)

                # TODO: Button that links to snippet in translations report when we have it
                messages.success(
                    request, _("The {} '{}' was successfully submitted for translation").format(model._meta.verbose_name.title(), (str(instance)))
                )

                if next_url:
                    return redirect(next_url)
                else:
                    return redirect("wagtailsnippets:edit", app_label, model_name, quote(pk))
    else:
        form = SubmitTranslationForm(instance)

    return render(
        request,
        "wagtail_localize/admin/submit_snippet_translation.html",
        {
            "app_label": app_label,
            "model_name": model_name,
            "model_verbose_name": model._meta.verbose_name.title(),
            "instance": instance,
            "form": form,
            "next_url": next_url,
        }
    )
