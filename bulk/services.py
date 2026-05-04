import csv
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import AutoField, BigAutoField, ForeignKey, ManyToManyField
from django.utils.dateparse import parse_date, parse_datetime, parse_time


def exportable_fields(model):
    fields = []
    for field in model._meta.fields:
        if isinstance(field, (AutoField, BigAutoField)):
            fields.append(field.name)
            continue

        if getattr(field, "editable", True):
            fields.append(field.name)

    return fields


def importable_fields(model):
    fields = []
    for field in model._meta.fields:
        if isinstance(field, (AutoField, BigAutoField)):
            fields.append(field.name)
            continue

        if isinstance(field, ManyToManyField):
            continue

        if getattr(field, "editable", True):
            fields.append(field.name)

    return fields


def field_reference(model):
    return [
        {
            "name": field.name,
            "type": field.get_internal_type(),
            "required": not field.blank and not field.null,
        }
        for field in model._meta.fields
        if field.name in importable_fields(model)
    ]


def sample_csv_response(model):
    output = io.StringIO()
    writer = csv.writer(output)

    fields = importable_fields(model)
    writer.writerow(fields)
    writer.writerow(["" for _ in fields])

    return output.getvalue()


def queryset_to_csv(model, queryset):
    output = io.StringIO()
    writer = csv.writer(output)

    fields = exportable_fields(model)
    writer.writerow(fields)

    for obj in queryset:
        row = []
        for field_name in fields:
            value = getattr(obj, field_name, "")

            if hasattr(value, "pk"):
                value = value.pk

            row.append(value if value is not None else "")

        writer.writerow(row)

    return output.getvalue()


def parse_boolean(value):
    return str(value).strip().lower() in ["1", "true", "yes", "y", "on"]


def parse_value(field, raw_value):
    if raw_value is None:
        return None

    value = str(raw_value).strip()

    if value == "":
        if field.null or field.blank or field.has_default():
            return None
        return ""

    internal_type = field.get_internal_type()

    if isinstance(field, ForeignKey):
        related_model = field.remote_field.model

        try:
            return related_model.objects.get(pk=value)
        except related_model.DoesNotExist:
            raise ValidationError(
                f"Related {related_model.__name__} with ID '{value}' does not exist."
            )

    if internal_type in [
        "IntegerField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "SmallIntegerField",
        "BigIntegerField",
    ]:
        return int(value)

    if internal_type == "FloatField":
        return float(value)

    if internal_type == "DecimalField":
        return Decimal(value.replace(",", ""))

    if internal_type in ["BooleanField", "NullBooleanField"]:
        return parse_boolean(value)

    if internal_type == "DateField":
        parsed = parse_date(value)
        if parsed is None:
            raise ValidationError(f"Invalid date '{value}'. Use YYYY-MM-DD.")
        return parsed

    if internal_type == "DateTimeField":
        parsed = parse_datetime(value)
        if parsed is None:
            raise ValidationError(f"Invalid datetime '{value}'. Use YYYY-MM-DD HH:MM[:SS].")
        return parsed

    if internal_type == "TimeField":
        parsed = parse_time(value)
        if parsed is None:
            raise ValidationError(f"Invalid time '{value}'. Use HH:MM[:SS].")
        return parsed

    return value


def import_csv(model, uploaded_file, update_existing=True):
    result = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "errors": [],
    }

    try:
        decoded = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        result["failed"] = 1
        result["errors"].append("File encoding error. Save the file as UTF-8 CSV.")
        return result

    reader = csv.DictReader(io.StringIO(decoded))

    if not reader.fieldnames:
        result["failed"] = 1
        result["errors"].append("CSV has no header row.")
        return result

    allowed = set(importable_fields(model))
    model_fields = {field.name: field for field in model._meta.fields}
    pk_name = model._meta.pk.name

    headers = [h.strip() for h in reader.fieldnames if h]
    unknown = [header for header in headers if header not in allowed]

    if unknown:
        result["failed"] = 1
        result["errors"].append(
            f"Unknown columns: {', '.join(unknown)}. Allowed columns: {', '.join(sorted(allowed))}"
        )
        return result

    for row_number, row in enumerate(reader, start=2):
        result["total"] += 1

        try:
            with transaction.atomic():
                pk_value = (row.get(pk_name) or "").strip()
                obj = None

                if update_existing and pk_value:
                    obj = model.objects.filter(pk=pk_value).first()

                if obj is None:
                    obj = model()

                for field_name, raw_value in row.items():
                    if not field_name:
                        continue

                    field_name = field_name.strip()

                    if field_name == pk_name and not getattr(model._meta.pk, "editable", False):
                        continue

                    field = model_fields.get(field_name)

                    if field is None or isinstance(field, ManyToManyField):
                        continue

                    parsed_value = parse_value(field, raw_value)

                    if parsed_value is None and field.has_default():
                        continue

                    setattr(obj, field_name, parsed_value)

                obj.full_clean()
                obj.save()

                result["success"] += 1

        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(f"Row {row_number}: {exc}")

    return result