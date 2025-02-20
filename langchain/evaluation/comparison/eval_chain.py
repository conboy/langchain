"""Base classes for comparing the output of two models."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from langchain.base_language import BaseLanguageModel
from langchain.callbacks.manager import Callbacks
from langchain.chains.llm import LLMChain
from langchain.evaluation.comparison.prompt import PROMPT, PROMPT_WITH_REFERENCE
from langchain.evaluation.schema import PairwiseStringEvaluator
from langchain.prompts.prompt import PromptTemplate
from langchain.schema import BaseOutputParser


class PairwiseStringResultOutputParser(BaseOutputParser[dict]):
    """A parser for the output of the PairwiseStringEvalChain."""

    @property
    def _type(self) -> str:
        return "pairwise_string_result"

    def parse(self, text: str) -> Any:
        """Parse the output text.

        Args:
            text (str): The output text to parse.

        Returns:
            Any: The parsed output.
        """
        reasoning, verdict = text.strip().rsplit("\n", maxsplit=1)
        verdict = verdict.strip("[").strip("]")
        if verdict not in {"A", "B", "C"}:
            raise ValueError(
                f"Invalid verdict: {verdict}. "
                "Verdict must be one of 'A', 'B', or 'C'."
            )
        # C means the models are tied. Return 'None' meaning no preference
        verdict_ = None if verdict == "C" else verdict
        score = {
            "A": 1,
            "B": 0,
            None: 0.5,
        }.get(verdict_)
        return {
            "reasoning": reasoning,
            "value": verdict_,
            "score": score,
        }


class PairwiseStringEvalChain(PairwiseStringEvaluator, LLMChain):
    """A chain for comparing the output of two models.

    Example:
    >>> from langchain.chat_models import ChatOpenAI
    >>> from langchain.evaluation.comparison import PairwiseStringEvalChain
    >>> llm = ChatOpenAI(temperature=0)
    >>> chain = PairwiseStringEvalChain.from_llm(llm=llm)
    >>> result = chain.evaluate_string_pairs(
    ...     input = "What is the chemical formula for water?",
    ...     prediction = "H2O",
    ...     prediction_b = (
    ...        "The chemical formula for water is H2O, which means"
    ...        " there are two hydrogen atoms and one oxygen atom."
    ...     referenc = "The chemical formula for water is H2O.",
    ... )
    >>> print(result["text"])
    # {
    #    "value": "B",
    #    "comment": "Both responses accurately state"
    #       " that the chemical formula for water is H2O."
    #       " However, Response B provides additional information"
    # .     " by explaining what the formula means.\n[[B]]"
    # }
    """

    output_parser: BaseOutputParser = Field(
        default_factory=PairwiseStringResultOutputParser
    )

    @property
    def requires_reference(self) -> bool:
        return "reference" in self.prompt.input_variables

    @property
    def requires_input(self) -> bool:
        return True

    @property
    def _skip_reference_warning(self) -> str:
        """Warning to show when reference is ignored."""
        return (
            f"Ignoring reference in {self.__class__.__name__}, as it is not expected."
            "\nTo use a reference, initialize PairwiseStringEvalChain with"
            " `requires_reference=True` or with a prompt with 'reference' as an"
            " input variable."
        )

    @classmethod
    def from_llm(
        cls,
        llm: BaseLanguageModel,
        *,
        prompt: Optional[PromptTemplate] = None,
        requires_reference: bool = False,
        **kwargs: Any,
    ) -> PairwiseStringEvalChain:
        """Initialize the PairwiseStringEvalChain from an LLM.

        Args:
            llm (BaseLanguageModel): The LLM to use.
            prompt (PromptTemplate, optional): The prompt to use.
            requires_reference (bool, optional): Whether to require a reference
                string. Defaults to False.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            PairwiseStringEvalChain: The initialized PairwiseStringEvalChain.
        """
        expected_input_vars = {"prediction", "prediction_b", "input"}
        if prompt is None:
            if requires_reference:
                expected_input_vars.add("reference")
                prompt_ = PROMPT_WITH_REFERENCE
            else:
                prompt_ = PROMPT
        else:
            if requires_reference:
                expected_input_vars.add("reference")
            prompt_ = prompt

        if expected_input_vars != set(prompt_.input_variables):
            raise ValueError(
                f"Input variables should be {expected_input_vars}, "
                f"but got {prompt_.input_variables}"
            )
        return cls(llm=llm, prompt=prompt_, **kwargs)

    def _prepare_input(
        self,
        prediction: str,
        prediction_b: str,
        input: Optional[str],
        reference: Optional[str],
    ) -> dict:
        input_ = {
            "prediction": prediction,
            "prediction_b": prediction_b,
        }
        if self.requires_input:
            if not input:
                raise ValueError("Input is require for this comparison evaluator")
            input_["input"] = input
        if self.requires_reference:
            if reference is None:
                raise ValueError("Reference is required for this comparison evaluator")
            input_["reference"] = reference
        return input_

    def _evaluate_string_pairs(
        self,
        *,
        prediction: str,
        prediction_b: str,
        input: Optional[str] = None,
        reference: Optional[str] = None,
        callbacks: Callbacks = None,
        **kwargs: Any,
    ) -> dict:
        """Evaluate whether output A is preferred to output B.

        Args:
            prediction (str): The output string from the first model.
            prediction_b (str): The output string from the second model.
            input (str): The input or task string.
            callbacks (Callbacks, optional): The callbacks to use.
            reference (str, optional): The reference string, if any.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            dict: A dictionary containing:
                - reasoning: The reasoning for the preference.
                - value: The preference value, which is either 'A', 'B', or None
                    for no preference.
                - score: The preference score, which is 1 for 'A', 0 for 'B',
                    and 0.5 for None.
        """
        input_ = self._prepare_input(prediction, prediction_b, input, reference)
        result = self(
            inputs=input_,
            callbacks=callbacks,
            **kwargs,
        )
        return result["text"]

    async def _aevaluate_string_pairs(
        self,
        *,
        prediction: str,
        prediction_b: str,
        reference: Optional[str] = None,
        input: Optional[str] = None,
        callbacks: Callbacks = None,
        **kwargs: Any,
    ) -> dict:
        """Asynchronously evaluate whether output A is preferred to output B.

        Args:
            prediction (str): The output string from the first model.
            prediction_b (str): The output string from the second model.
            input (str): The input or task string.
            callbacks (Callbacks, optional): The callbacks to use.
            reference (str, optional): The reference string, if any.
            **kwargs (Any): Additional keyword arguments.

        Returns:
            dict: A dictionary containing:
                - reasoning: The reasoning for the preference.
                - value: The preference value, which is either 'A', 'B', or None
                    for no preference.
                - score: The preference score, which is 1 for 'A', 0 for 'B',
                    and 0.5 for None.
        """
        input_ = self._prepare_input(prediction, prediction_b, input, reference)
        result = await self.acall(
            inputs=input_,
            callbacks=callbacks,
            **kwargs,
        )
        return result["text"]
