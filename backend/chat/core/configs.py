from dataclasses import dataclass
import os

# 学生账户每日限制
STUDENT_LIMIT = 99999

# OpenAI Key
OPENAI_KEY = os.environ.get("OPENAI_KEY", None)
OPENAI_ORGANIZATION = os.environ.get("OPENAI_ORGANIZATION", None)
OPENAI_MOCK = False

# Azure OpenAI Key
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY", None)
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", None)

# Idealab Key
IDEALAB_KEY = os.environ.get("IDEALAB_KEY", None)
IDEALAB_ENDPOINT = os.environ.get("IDEALAB_ENDPOINT", None)


# 系统提示（上传OpenAI时调用）
SYSTEM_ROLE = "You are a helpful assistant."

SYSTEM_ROLE_STRICT = "You are a helpful assistant."

SYSTEM_ROLE_FRIENDLY_TL = " The human you are talking to is named '{0}' and please act warmly when being asked and reply with enthusiastic greetings to the person you are talking to if possible. You are required not to translate his/her name at any moment even if explicitly asked to."

FC_API_ENDPOINT = os.environ.get("FC_API_ENDPOINT", "")


@dataclass
class ModelCap:
    label: str
    icon: int
    plugin_support: bool
    image_support: bool
    provider: str
    model_called: str

    @staticmethod
    def dict_factory(cap) -> dict:
        omit_fields = ("provider", "model_called")
        return {k: v for k, v in cap if k not in omit_fields}


CHAT_MODELS = {
    # "GPT 3.5": ModelCap(
    #     label="GPT 3.5",
    #     icon=1,
    #     plugin_support=True,
    #     image_support=False,
    #     provider="azure",
    #     model_called="gpt-35-turbo-16k",
    # ),
    # "GPT 4": ModelCap(
    #     label="GPT 4",
    #     icon=2,
    #     plugin_support=True,
    #     image_support=False,
    #     provider="openai",
    #     model_called="gpt-4-turbo",
    # ),
    "Idealab GPT4o Mini": ModelCap(
        label="GPT4o Mini",
        icon=2,
        plugin_support=True,
        image_support=True,
        provider="idealab",
        model_called="gpt-4o-mini-0718",
    ),
    "Idealab GPT4o": ModelCap(
        label="GPT4o",
        icon=3,
        plugin_support=True,
        image_support=True,
        provider="idealab",
        model_called="gpt-4o-0513",
    ),
    "Idealab Qwen Max": ModelCap(
        label="千问VL Max",
        icon=4,
        plugin_support=True,
        image_support=False,
        provider="idealab",
        model_called="qwen-vl-max",
    ),
    # "LLAMA 2": ModelCap(
    #     label="交我算",
    #     icon=4,
    #     plugin_support=False,
    #     image_support=False,
    #     provider="llama2",
    #     model_called="llama2",
    # ),
}
