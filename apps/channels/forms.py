from django import forms
from .models import Category, Channel


class AddChannelForm(forms.Form):
    channel_url = forms.CharField(
        max_length=500,
        label="YouTube Channel URL or @handle",
        widget=forms.TextInput(attrs={
            "placeholder": "https://www.youtube.com/@channelname or UC...",
            "class": "form-input",
        }),
    )
    summarize_enabled = forms.BooleanField(
        required=False,
        label="Summarize videos with Gemini",
        initial=False,
    )
    default_category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label="— No default category —",
        label="Default Category",
        widget=forms.Select(attrs={"class": "form-input"}),
    )
