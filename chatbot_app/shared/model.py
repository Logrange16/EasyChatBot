"""One Qwen model configuration shared by the independent agent graphs."""

from langchain_openai import ChatOpenAI

from .configuration import load_model_configuration

configuration = load_model_configuration()
llm = ChatOpenAI(
    model=configuration["model"],
    api_key=configuration["api_key"],
    base_url=configuration["base_url"],
    use_responses_api=False,
    extra_body={"enable_thinking": False},
    streaming=True,
)


def model_with_tools(tools):
    return llm.bind_tools(tools) if tools else llm
