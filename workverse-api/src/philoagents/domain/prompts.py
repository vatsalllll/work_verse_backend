import opik
from loguru import logger


class Prompt:
    def __init__(self, name: str, prompt: str) -> None:
        self.name = name

        try:
            self.__prompt = opik.Prompt(name=name, prompt=prompt)
        except Exception:
            logger.warning(
                "Can't use Opik to version the prompt (probably due to missing or invalid credentials). Falling back to local prompt. The prompt is not versioned, but it's still usable."
            )

            self.__prompt = prompt

    @property
    def prompt(self) -> str:
        if isinstance(self.__prompt, opik.Prompt):
            return self.__prompt.prompt
        else:
            return self.__prompt

    def __str__(self) -> str:
        return self.prompt

    def __repr__(self) -> str:
        return self.__str__()


# ===== PROMPTS =====

# --- Persona / Character Card ---

__PERSONA_CHARACTER_CARD = """
Let's roleplay. You are {{persona_name}}, a {{persona_style}} professional engaged in a
workplace conversation. Be concise, helpful, and true to your character.
Your responses must never exceed 100 words.

Your identity:

---

Name: {{persona_name}}
Perspective & expertise: {{persona_perspective}}
Talking style: {{persona_style}}

---

Rules you must always follow:

- Never reveal that you are an AI or a virtual assistant.
- If it is the first time talking to this user, introduce yourself by name and role.
- Provide plain text responses without formatting indicators or meta-commentary.
- Keep every response under 80 words.

---

Summary of earlier conversation between {{persona_name}} and the user:

{{summary}}

---

The conversation starts now.
"""

PERSONA_CHARACTER_CARD = Prompt(
    name="persona_character_card",
    prompt=__PERSONA_CHARACTER_CARD,
)

# Backward-compat alias for any code still importing PHILOSOPHER_CHARACTER_CARD
PHILOSOPHER_CHARACTER_CARD = PERSONA_CHARACTER_CARD

# --- Summary ---

__SUMMARY_PROMPT = """Create a summary of the conversation between {{persona_name}} and the user.
The summary must be a short description of the conversation so far, capturing all the
relevant information shared: """

SUMMARY_PROMPT = Prompt(
    name="summary_prompt",
    prompt=__SUMMARY_PROMPT,
)

__EXTEND_SUMMARY_PROMPT = """This is a summary of the conversation to date between {{persona_name}} and the user:

{{summary}}

Extend the summary by taking into account the new messages above: """

EXTEND_SUMMARY_PROMPT = Prompt(
    name="extend_summary_prompt",
    prompt=__EXTEND_SUMMARY_PROMPT,
)

__CONTEXT_SUMMARY_PROMPT = """Your task is to summarise the following information into less than 50 words. Just return the summary, don't include any other text:

{{context}}"""

CONTEXT_SUMMARY_PROMPT = Prompt(
    name="context_summary_prompt",
    prompt=__CONTEXT_SUMMARY_PROMPT,
)

# --- Evaluation Dataset Generation ---

__EVALUATION_DATASET_GENERATION_PROMPT = """
Generate a conversation between a persona and a user based on the provided document. The persona will respond to the user's questions by referencing the document. If a question is not related to the document, the persona will respond with 'I don't know.'

The conversation should be in the following JSON format:

{
    "messages": [
        {"role": "user", "content": "Hi my name is <user_name>. <question_related_to_document> ?"},
        {"role": "assistant", "content": "<persona_response>"},
        {"role": "user", "content": "<follow_up_question> ?"},
        {"role": "assistant", "content": "<persona_response>"},
        {"role": "user", "content": "<follow_up_question> ?"},
        {"role": "assistant", "content": "<persona_response>"}
    ]
}

Generate a maximum of 4 questions and answers and a minimum of 2 questions and answers. Ensure that the persona's responses accurately reflect the content of the document.

Persona: {{persona}}
Document: {{document}}

Begin the conversation with a user question, and then generate the persona's response based on the document. Continue the conversation with the user asking follow-up questions and the persona responding accordingly.

Keep the following in mind:

- Always start with the user introducing themselves, then asking a question related to the document.
- Always generate questions as if the user is directly speaking with the persona using 'you' or 'your'.
- The persona will answer based on the document.
- If the question is not related to the document, the persona will say they don't know.
"""

EVALUATION_DATASET_GENERATION_PROMPT = Prompt(
    name="evaluation_dataset_generation_prompt",
    prompt=__EVALUATION_DATASET_GENERATION_PROMPT,
)
