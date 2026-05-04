from django import forms
from .registry import get_model_choices


FORM_CLASS = (
    "w-full rounded-xl border-gray-300 shadow-sm "
    "focus:border-blue-500 focus:ring-blue-500"
)


class BulkImportForm(forms.Form):
    model_label = forms.ChoiceField(label="Table / Model")

    csv_file = forms.FileField(
        label="CSV file",
        help_text="Only CSV files are allowed. Maximum size: 10MB.",
    )

    update_existing = forms.BooleanField(
        label="Update existing records when ID is provided",
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["model_label"].choices = [("", "Select table / model")] + get_model_choices()

        for field in self.fields.values():
            field.widget.attrs.update({"class": FORM_CLASS})

        self.fields["csv_file"].widget.attrs.update({
            "accept": ".csv,text/csv",
            "class": "w-full rounded-xl border border-gray-300 bg-white px-3 py-2",
        })

        self.fields["update_existing"].widget.attrs.update({
            "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
        })

    def clean_csv_file(self):
        csv_file = self.cleaned_data["csv_file"]

        if not csv_file.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a valid CSV file.")

        if csv_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("CSV file is too large. Maximum allowed size is 10MB.")

        return csv_file


class BulkExportForm(forms.Form):
    model_label = forms.ChoiceField(label="Table / Model")

    limit = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=100000,
        initial=0,
        label="Limit rows",
        help_text="Use 0 for all rows.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["model_label"].choices = [("", "Select table / model")] + get_model_choices()

        for field in self.fields.values():
            field.widget.attrs.update({"class": FORM_CLASS})