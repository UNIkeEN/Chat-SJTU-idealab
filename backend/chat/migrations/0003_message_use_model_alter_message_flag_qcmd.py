# Generated by Django 4.2.2 on 2023-07-10 02:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0002_message_flag_qcmd_session_is_renamed_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='use_model',
            field=models.CharField(default='', max_length=50, verbose_name='使用模型'),
        ),
        migrations.AlterField(
            model_name='message',
            name='flag_qcmd',
            field=models.BooleanField(default=False, verbose_name='是否为快捷指令回复'),
        ),
    ]
