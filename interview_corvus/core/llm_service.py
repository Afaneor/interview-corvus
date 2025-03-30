from typing import List, Type, TypeVar

from llama_index.core.base.llms.types import ChatMessage, ImageBlock, \
    MessageRole
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.llms.openai import OpenAI
from loguru import logger
from pydantic import BaseModel
from PyQt6.QtCore import QObject, pyqtSignal

from interview_corvus.config import settings
from interview_corvus.core.models import CodeOptimization, CodeSolution
from interview_corvus.core.prompt_manager import PromptManager
from interview_corvus.security.api_key_manager import APIKeyManager

T = TypeVar("T", bound=BaseModel)


class LLMService(QObject):
    """Service for interacting with LLM through LlamaIndex."""

    # Signals for responses
    completion_finished = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        """Initialize the LLM service with configured settings."""
        super().__init__()
        api_key = APIKeyManager().get_api_key()

        self.llm = OpenAI(
            model=settings.llm.model,
            temperature=settings.llm.temperature,
            api_key=api_key,
            max_retries=settings.llm.max_retries,
            timeout=settings.llm.timeout,
        )

        # Initialize chat engine that will maintain conversation history
        self.chat_engine = SimpleChatEngine.from_defaults(
            llm=self.llm,
        )
        logger.info(f"LLM Service initialized with model: {settings.llm.model}")

    def reset_chat_history(self):
        """Reset the chat history."""
        logger.info("Resetting chat history")
        # Recreate chat engine to clear the history
        self.chat_engine = SimpleChatEngine.from_defaults(
            llm=self.llm,
        )

    def query_structured(self, prompt: str, output_cls: Type[T]) -> T:
        """
        Send a query to the LLM and get a structured response.

        Args:
            prompt: The prompt text to send to the LLM
            output_cls: The Pydantic model class for structuring the response

        Returns:
            An instance of the provided Pydantic model with the structured response
        """
        logger.info(f"Sending structured query: {prompt[:50]}...")

        response = self.chat_engine.chat(prompt)
        response_text = response.response

        # Store the assistant response
        logger.info(f"Got response (length: {len(response_text)})")

        # Parse into structured format
        structured_llm = self.llm.as_structured_llm(output_cls=output_cls)
        try:
            result = structured_llm.complete(response_text)
            return result
        except Exception as e:
            logger.info(f"Error parsing structured response: {e}")
            # Create basic fallback instance
            raise e

    def get_code_optimization(
        self, code: str, language: str = None
    ) -> CodeOptimization:
        """
        Get an optimized version of provided code.

        Args:
            code: The code to optimize
            language: The programming language of the code (defaults to settings)

        Returns:
            A structured code optimization response
        """
        # Use default language from settings if none provided
        if language is None:
            language = settings.default_language

        prompt_manager = PromptManager()
        prompt = prompt_manager.get_prompt(
            "code_optimization", code=code, language=language
        )

        return self.query_structured(prompt, CodeOptimization)

    def get_solution_from_screenshots(
        self, screenshot_paths: List[str], language: str = None
    ) -> CodeSolution:
        """
        Get a solution based on multiple screenshots of a programming problem.

        Args:
            screenshot_paths: List of paths to the screenshot files
            language: The programming language to use for the solution (defaults to settings)

        Returns:
            A structured code solution response
        """
        # Use default language from settings if none provided
        if language is None:
            language = settings.default_language

        # For multimodal requests, using direct OpenAI API call through LlamaIndex
        prompt_manager = PromptManager()

        # Get the screenshot prompt with language
        prompt_text = prompt_manager.get_prompt(
            "screenshot_solution", language=language
        )

        logger.info(f"Processing {len(screenshot_paths)} screenshots")

        # Create a system message with the prompt text
        system = ChatMessage(
            role=MessageRole.SYSTEM,
            content=prompt_text,
        )

        # Initialize chat messages with the system message
        chat_messages = [system]

        # Add each screenshot as a user message with an image block
        for path in screenshot_paths:
            logger.info(f"Adding screenshot: {path}")
            screenshot = ChatMessage(
                role=MessageRole.USER,
                blocks=[
                    ImageBlock(
                        path=path,
                    )
                ],
            )
            chat_messages.append(screenshot)

        # For processing screenshots with history context
        structured = self.llm.as_structured_llm(output_cls=CodeSolution)
        response = structured.chat(chat_messages)
        return response.raw
