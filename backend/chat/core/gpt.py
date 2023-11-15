import dacite
from chat.core.errors import ChatError
from chat.models.message import Message
from .testdata.lipsum import LIPSUM
from .configs import *
from .plugins.fc import FCSpec

from typing_extensions import Self
from typing import Awaitable, Callable, Union
from dataclasses import asdict, dataclass
from abc import ABC, abstractmethod
import functools
import tenacity
import logging
import openai

logger = logging.getLogger(__name__)

openai.proxy = os.getenv("OPENAI_PROXY", None)


@dataclass
class GPTUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AbstractRespHandler(ABC):
    @abstractmethod
    def set_next(self, handler: Self) -> Self:
        raise NotImplementedError()

    @abstractmethod
    async def handle(self, msg: list, response: dict) -> Message:
        raise NotImplementedError()


class RespHandler(AbstractRespHandler):
    __next: Union[Self, None] = None

    def __init__(self, model: str):
        self.model = model

    def extract_finish_reason(self, response: dict) -> str:
        return response["choices"][-1].get("finish_reason", "stop")

    def extract_content(self, response: dict) -> str:
        try:
            content: str = response["choices"][-1]["message"]["content"]
            return content
        except KeyError:
            raise ChatError("服务器网络错误，请稍候重试")

    def extract_usage(self, response: dict) -> GPTUsage:
        try:
            return dacite.from_dict(GPTUsage, response["usage"])

        except KeyError:
            return GPTUsage(0, 0, 0)

    def construct_message(self, response: dict) -> Message:
        usage = self.extract_usage(response)
        return Message(
            sender=0,
            flag_qcmd=False,
            content=self.extract_content(response),
            interrupted=0,
            plugin_group=response.get("plugin_group", ""),
            use_model=self.model,
            completion_tokens=usage.completion_tokens,
            prompt_tokens=usage.prompt_tokens,
        )

    def set_next(self, handler: Self) -> Self:
        self.__next = handler
        return handler

    async def handle(self, msg: list, response: dict) -> Message:
        if self.__next:
            return await self.__next.handle(msg, response)
        return await super().handle(msg, response)


class LengthRespHandler(RespHandler):
    def __init__(self, model: str):
        return super().__init__(model)

    async def handle(self, msg: list, response: dict) -> Message:
        if self.extract_finish_reason(response) == "length":
            message = self.construct_message(response)
            message.interrupted = 1
            return message
        else:
            return await super().handle(msg, response)


class FunctionRespHandler(RespHandler):
    def __init__(
        self, model: str, fc_map: dict, gpt: Callable[[list], Awaitable[dict]]
    ):
        self.gpt = gpt
        self.fc_map = fc_map
        return super().__init__(model)

    async def handle(self, msg: list, response: dict) -> Message:
        if self.extract_finish_reason(response) == "function_call":
            fc_gpt_usage = self.extract_usage(response)
            fc_gpt_resp: dict[str, str] = response["choices"][0]["message"][
                "function_call"
            ]
            fc = self.fc_map[fc_gpt_resp["name"]]
            fc_plugin_group = fc.group_id
            arguments = fc_gpt_resp["arguments"]
            try:
                fc_success, fc_content = await fc.exec(arguments)
            except Exception:
                raise ChatError("服务器网络错误，请稍候重试")

            if not fc_success:
                raise ChatError(fc_content)

            else:
                msg.append(
                    {
                        "role": "function",
                        "name": fc.definition.name,
                        "content": fc_content,
                    }
                )

            response = await self.gpt(msg)
            response["plugin_group"] = fc_plugin_group

            message = await super().handle(msg, response)
            message.prompt_tokens += fc_gpt_usage.prompt_tokens
            message.completion_tokens += fc_gpt_usage.completion_tokens
            return message
        return await super().handle(msg, response)


class StopRespHandler(RespHandler):
    def __init__(self, model: str):
        return super().__init__(model)

    async def handle(self, msg: list, response: dict) -> Message:
        if self.extract_finish_reason(response) == "stop":
            return self.construct_message(response)
        else:
            return await super().handle(msg, response)


class AbstractGPTConnection(ABC):
    @abstractmethod
    async def interact(
        self,
        msg: list,
        temperature=0.5,
        max_tokens=1000,
        selected_plugins: list[FCSpec] = [],
    ) -> Message:
        raise NotImplementedError()


class MockGPTConnection(AbstractGPTConnection):
    def __init__(self, model: str, mode: str = "oneshot"):
        self.model = model

    async def interact(
        self,
        msg: list,
        temperature=0.5,
        max_tokens=1000,
        selected_plugins: list[FCSpec] = [],
    ) -> Message:
        return Message(
            sender=0,
            flag_qcmd=False,
            content=LIPSUM,
            interrupted=0,
            plugin_group="",
            use_model=self.model,
        )


class GPTConnection(AbstractGPTConnection):
    def __init__(self, model_engine: str = "Azure GPT3.5", mode: str = "oneshot"):
        self.displayed_model = model_engine
        self.__model_kwargs = {}
        if model_engine == "OpenAI GPT4":
            self.__model_called = "gpt-4"
            self.__setup_gpt_environment = self.__setup_openai
        elif model_engine == "Azure GPT3.5":
            self.__model_called = "gpt-35-turbo-16k"
            self.__setup_gpt_environment = self.__setup_azure
        elif model_engine == "LLAMA 2":
            self.__model_called = "llama2"
            self.__setup_gpt_environment = self.__setup_llama2
        else:
            raise ChatError("模型不存在")

    def __setup_azure(self):
        openai.api_type = "azure"
        openai.organization = None
        openai.api_key = AZURE_OPENAI_KEY
        openai.api_base = AZURE_OPENAI_ENDPOINT
        openai.api_version = "2023-07-01-preview"
        self.__model_kwargs["engine"] = self.__model_called

    def __setup_openai(self):
        openai.api_type = "open_ai"
        openai.organization = OPENAI_ORGANIZATION
        openai.api_key = OPENAI_KEY
        openai.api_base = "https://api.openai.com/v1"
        openai.api_version = None
        self.__model_kwargs["model"] = self.__model_called

    def __setup_llama2(self):
        openai.api_type = "open_ai"
        openai.organization = None
        openai.api_key = "llama2"
        openai.api_base = LLAMA2_ENDPOINT
        self.__model_kwargs["model"] = self.__model_called

    def __setup_plugins(self, selected_plugins: list[FCSpec]):
        if selected_plugins:
            self.__model_kwargs["functions"] = [
                asdict(fc_spec.definition) for fc_spec in selected_plugins
            ]
        self.fc_map = {fc_spec.definition.name: fc_spec for fc_spec in selected_plugins}

    def __setup_gpt(self, temperature: float, max_tokens: int):
        self.gpt = functools.partial(
            self.__interact_with_gpt, temperature=temperature, max_tokens=max_tokens
        )

    def __setup_handlers(self):
        self.__handler = FunctionRespHandler(
            self.displayed_model, self.fc_map, self.gpt
        )
        self.__handler.set_next(StopRespHandler(self.displayed_model)).set_next(
            LengthRespHandler(self.displayed_model)
        )

    def __pre_interact(
        self, temperature: float, max_tokens: int, selected_plugins: list[FCSpec]
    ):
        self.__setup_gpt_environment()
        self.__setup_plugins(selected_plugins)
        self.__setup_gpt(temperature, max_tokens)
        self.__setup_handlers()

    async def __post_interact(self, msg: list, response: dict) -> Message:
        return await self.__handler.handle(msg, response)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_random_exponential(min=1, max=5),
        retry=tenacity.retry_if_exception_type(openai.error.OpenAIError),
        before=tenacity.before_log(logger, logging.DEBUG),
        reraise=True,
    )
    async def __interact_with_gpt(
        self,
        msg: list,
        temperature: float,
        max_tokens: int,
    ):
        try:
            response = await openai.ChatCompletion.acreate(
                messages=msg,
                temperature=temperature,
                max_tokens=max_tokens,
                **self.__model_kwargs,
            )
            print(response)
            assert isinstance(response, dict)
            return response
        except openai.error.InvalidRequestError as e:
            logger.error(e)
            raise ChatError("请求失败，输入可能过长，请前往“偏好设置”减少“附带历史消息数”或缩短输入")

        except openai.error.AuthenticationError as e:
            logger.error(e)
            raise ChatError("验证失败，请联系管理员")

        except openai.error.OpenAIError as _:
            raise

        except Exception as e:
            logger.error(e)
            raise ChatError("服务器遇到未知错误")

    async def interact(
        self,
        msg: list,
        temperature=0.5,
        max_tokens=1000,
        selected_plugins: list[FCSpec] = [],
    ) -> Message:
        """
        使用openai包与openai api进行交互
        Args:
            msg: 用户输入的消息
            temperature: 生成文本的多样性
            max_tokens: 生成文本的长度
            **kwargs: 其他参数
        Returns:
            response: Message对象
        Error:
            ChatError: 若出错则抛出以及对应的status code
        """
        self.__pre_interact(temperature, max_tokens, selected_plugins)

        try:
            response = await self.gpt(msg)
            assert isinstance(response, dict)
            return await self.__post_interact(msg, response)

        except openai.error.RateLimitError as e:
            logger.error(e)
            raise ChatError("API受限，请稍作等待后重试，若一直受限请联系管理员")

        except openai.error.OpenAIError as e:
            logger.error(e)
            raise ChatError("API或网络错误，请稍作等待后重试")


class GPTConnectionFactory:
    def __init__(self):
        self.__model_engine: str = "nil"
        self.__mock: bool = False

    def model_engine(self, model_engine: str = "Azure GPT3.5"):
        self.__model_engine = model_engine
        return self

    def mock(self, mock: bool):
        self.__mock = mock
        return self

    def build(self) -> AbstractGPTConnection:
        if self.__mock:
            return MockGPTConnection(self.__model_engine)
        else:
            return GPTConnection(self.__model_engine)


"""
与GPT交互，两方API略有不同，但输入输出几乎一致
@msg 用户发送的信息,封装成字典的形式
    需要是如下的结构
    [ {'role':'system', 'content':'xxx'},
        {'role':'user', 'content':'xxx'}
        {'role':'assistant', 'content':'xxx'}
    ]
    system表示对系统的指示,提供整体的指导方针,如'你是学习助手,你的任务是帮助用户学习'，之后输入用户和gpt的多轮对话;
    user表示用户的输入,可以有多轮对话;
    assistant表示gpt的回复,可以是多轮的对话

@model_engine 语言模型的名字

@temperature 代表了回复的自由度,越大则回复的内容越自由. 如果需要要可预测的回复内容,可以设置为0,每次回复的内容相同; 
    如果需要更加自由的回复,可以设置为1,每次回复的内容都不同

@max_tokens 代表了回复的最大长度,如果设置为0,则回复的内容为空;
@return(flag, response) flag为真表示无错误，response为语言模型的回复或错误JSON
"""
