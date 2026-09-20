from django.db import migrations


def encrypt_existing(apps, schema_editor):
    for model_name, fields in [('User', ['phone', 'first_name', 'contact']), ('VerificationCode', ['phone'])]:
        model = apps.get_model('library', model_name)
        for obj in model.objects.all().iterator():
            obj.save(update_fields=fields)


def decrypt_existing(apps, schema_editor):
    quote = schema_editor.quote_name
    for model_name, fields in [('User', ['phone', 'first_name', 'contact']), ('VerificationCode', ['phone'])]:
        model = apps.get_model('library', model_name)
        for obj in model.objects.all().iterator():
            columns = ', '.join(f'{quote(field)} = %s' for field in fields)
            schema_editor.execute(f'UPDATE {quote(model._meta.db_table)} SET {columns} WHERE id = %s',
                [getattr(obj, field) for field in fields]+[obj.pk])


class Migration(migrations.Migration):
    dependencies = [('library', '0004_alter_user_contact_alter_user_first_name_and_more')]
    operations = [migrations.RunPython(encrypt_existing, decrypt_existing)]
