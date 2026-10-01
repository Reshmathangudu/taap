import os

import truststore
from dotenv import find_dotenv, load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from .models import (
    TestCaseGenerationInput,
    TestCaseGenerationResult,
)

from .prompt import TEST_CASE_GENERATION_PROMPT


# Corporate networks often intercept outbound TLS with a proxy root CA that
# certifi's bundle doesn't trust; the OS trust store does. Route SSL through
# the OS store instead so the OpenAI/LiteLLM HTTPS calls below succeed.
truststore.inject_into_ssl()

load_dotenv(find_dotenv())


MODEL_NAME = os.getenv(
    "TEST_CASE_MODEL",
    "openai/gpt-4.1",
)


test_case_generation_agent = LlmAgent(

    name="test_case_generation_agent",

    description=(
        "Analyzes Jira requirements and existing test cases, "
        "identifies test coverage gaps, and generates only "
        "new non-duplicate test cases."
    ),

    model=LiteLlm(
        model=MODEL_NAME
    ),

    instruction=TEST_CASE_GENERATION_PROMPT,

    input_schema=TestCaseGenerationInput,

    output_schema=TestCaseGenerationResult,

    output_key="test_case_generation_result",
)


root_agent = test_case_generation_agent
