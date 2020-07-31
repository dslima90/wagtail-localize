from django.shortcuts import render


def translations_report(request):
    return render(request, 'wagtail_localize/translations_report.html')
