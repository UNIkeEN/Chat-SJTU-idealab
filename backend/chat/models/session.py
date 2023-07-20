from django.db import models
from django.contrib.auth.models import User
from asgiref.sync import sync_to_async

class Session(models.Model):
    class Meta:
        verbose_name = '会话'
        verbose_name_plural = verbose_name

    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=100)
    is_renamed = models.BooleanField(default=False) # 是否被改名过（不直接检测名称是否为默认，保证用户改回为默认的情况）

    def __str__(self):
        return f"{self.user} : {self.name}"
    
    async def get_recent_n(self, n:int): # 获取最近n条
        def wrapper(n:int):
            return list(self.message_set.order_by('-timestamp')[:n])

        messages = await sync_to_async(wrapper)(n)

        return messages[::-1]
    
    # def delete_last_message(self): # 删去最新一条
    #     recent_message = self.message_set.order_by('-timestamp').first()
    #     if recent_message:
    #         recent_message.delete()
