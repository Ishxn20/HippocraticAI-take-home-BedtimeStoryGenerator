import os
import re
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "gpt-3.5-turbo"
MAX_REFINEMENT_ITERATIONS = 5
JUDGE_THRESHOLD = 7

API_MAX_RETRIES = 3
API_RETRY_BACKOFF_SECONDS = 1.5

STORY_MAX_TOKENS = 2000
ANALYZER_MAX_TOKENS = 500
JUDGE_MAX_TOKENS = 900

# Interactive Choice Mode constants
CHOICE_MODE_MAX_STEPS = 3
CHOICE_PROPOSAL_MAX_TOKENS = 250
CHOICE_CONTINUATION_MAX_TOKENS = 900

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Put it in your environment or a .env file.")

client = OpenAI(api_key=api_key)


class StoryCategory(Enum):
    ADVENTURE = "adventure"
    FANTASY = "fantasy"
    ANIMAL = "animal"
    FRIENDSHIP = "friendship"
    BEDTIME = "bedtime"
    EDUCATIONAL = "educational"
    FUNNY = "funny"


@dataclass
class StoryRequest:
    raw_input: str
    category: StoryCategory
    characters: List[str]
    themes: List[str]
    setting: str
    tone: str


@dataclass
class JudgeFeedback:
    overall_score: int  # 1-10
    age_appropriateness: int
    engagement: int
    moral_clarity: int
    story_structure: int
    language_quality: int
    feedback: str
    suggestions: List[str]


@dataclass
class Story:
    title: str
    content: str
    moral: str
    version: int


def clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
        return max(lo, min(hi, v))
    except Exception:
        return default


def safe_split_csv(text: str) -> List[str]:
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


def normalize_tone(tone: str) -> str:
    allowed = {"whimsical", "exciting", "calming", "humorous", "heartwarming", "inspiring"}
    t = (tone or "").strip().lower()
    return t if t in allowed else "whimsical"

# Utility Functions
def format_story_for_context(story: Story) -> str:
    return f"TITLE: {story.title}\nSTORY:\n{story.content}\nMORAL: {story.moral}\nVERSION: {story.version}"


def format_feedback_for_context(feedback: JudgeFeedback, round_num: int) -> str:
    suggestions_text = "\n".join(f"- {s}" for s in feedback.suggestions) if feedback.suggestions else "- (no suggestions returned)"
    return (
        f"ROUND {round_num} FEEDBACK\n"
        f"OVERALL_SCORE: {feedback.overall_score}\n"
        f"AGE_APPROPRIATENESS: {feedback.age_appropriateness}\n"
        f"ENGAGEMENT: {feedback.engagement}\n"
        f"MORAL_CLARITY: {feedback.moral_clarity}\n"
        f"STORY_STRUCTURE: {feedback.story_structure}\n"
        f"LANGUAGE_QUALITY: {feedback.language_quality}\n"
        f"FEEDBACK: {feedback.feedback}\n"
        f"SUGGESTIONS:\n{suggestions_text}\n"
    )


# LLM Interaction with Retries

def call_model(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 3000,
    temperature: float = 0.7,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_err: Optional[Exception] = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as e:
            last_err = e
            if attempt < API_MAX_RETRIES:
                time.sleep(API_RETRY_BACKOFF_SECONDS * attempt)
            else:
                break

    raise RuntimeError(f"OpenAI API call failed after {API_MAX_RETRIES} attempts: {last_err}")


# Story Request Analyzer

ANALYZER_SYSTEM_PROMPT = """You are a story request analyzer for a children's bedtime story generator (ages 5-10).
Analyze the user's request and extract structured information.

Respond ONLY in this exact format (one per line):
CATEGORY: [adventure|fantasy|animal|friendship|bedtime|educational|funny]
CHARACTERS: [comma-separated list of characters mentioned or suggested]
THEMES: [comma-separated list of themes like courage, friendship, kindness, curiosity]
SETTING: [where the story takes place]
TONE: [whimsical|exciting|calming|humorous|heartwarming|inspiring]

If information is not provided, make reasonable child-friendly suggestions.
Do not add extra lines.
"""


def parse_analyzer_response(response: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for line in (response or "").strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip().upper()] = value.strip()
    return parsed


def analyze_request(user_input: str) -> StoryRequest:
    prompt = f"Analyze this bedtime story request: {user_input}"

    response = call_model(
        prompt,
        ANALYZER_SYSTEM_PROMPT,
        max_tokens=ANALYZER_MAX_TOKENS,
        temperature=0.2,
    )

    parsed = parse_analyzer_response(response)

    category_map = {cat.value: cat for cat in StoryCategory}
    category_str = (parsed.get("CATEGORY", "bedtime") or "bedtime").strip().lower()
    category = category_map.get(category_str, StoryCategory.BEDTIME)

    characters = safe_split_csv(parsed.get("CHARACTERS", ""))
    themes = safe_split_csv(parsed.get("THEMES", ""))

    setting = parsed.get("SETTING", "").strip() or "a magical land"
    tone = normalize_tone(parsed.get("TONE", ""))

    return StoryRequest(
        raw_input=user_input,
        category=category,
        characters=characters,
        themes=themes,
        setting=setting,
        tone=tone,
    )


# Storyteller System

def get_storyteller_system_prompt(category: StoryCategory) -> str:
    base_prompt = """You are a master children's storyteller creating bedtime stories for ages 5-10.

STORY STRUCTURE (Follow the classic story arc):
1. OPENING: Introduce the main character and their world in a cozy, inviting way
2. INCITING INCIDENT: Something happens that starts the adventure
3. RISING ACTION: The character faces challenges and meets helpers
4. CLIMAX: The most exciting moment where the character must be brave/clever/kind
5. FALLING ACTION: The problem begins to resolve
6. RESOLUTION: A satisfying, peaceful ending perfect for bedtime

GUIDELINES:
- Use simple, vivid language that children can understand
- Include sensory details (colors, sounds, textures)
- Add gentle repetition and rhythm where appropriate
- Include dialogue to bring characters to life
- Ensure a clear, positive moral lesson
- End with a calming, sleep-inducing conclusion
- Story length: 400-600 words
- Avoid scary elements, violence, or anything inappropriate for young children

FORMAT YOUR RESPONSE AS:
TITLE: [Story Title]
STORY:
[The full story text]
MORAL: [The lesson of the story in one sentence]"""

    category_additions = {
        StoryCategory.ADVENTURE: "\n\nADVENTURE FOCUS: Include exciting discoveries, brave choices, and exploration. The character should show courage but always stay safe.",
        StoryCategory.FANTASY: "\n\nFANTASY FOCUS: Include magical elements like talking animals, enchanted objects, or gentle magic. Keep magic whimsical and wonder-inducing.",
        StoryCategory.ANIMAL: "\n\nANIMAL FOCUS: Feature animals with relatable personalities. Show their natural behaviors mixed with child-like emotions and adventures.",
        StoryCategory.FRIENDSHIP: "\n\nFRIENDSHIP FOCUS: Emphasize cooperation, sharing, understanding differences, and the joy of having friends.",
        StoryCategory.BEDTIME: "\n\nBEDTIME FOCUS: Create a soothing atmosphere. Include cozy imagery like warm blankets, twinkling stars, and peaceful nights.",
        StoryCategory.EDUCATIONAL: "\n\nEDUCATIONAL FOCUS: Weave in a learning element naturally (counting, colors, nature facts, kindness lessons).",
        StoryCategory.FUNNY: "\n\nHUMOR FOCUS: Include silly situations, playful wordplay, and gentle humor that makes children giggle.",
    }

    return base_prompt + category_additions.get(category, "")


def parse_story_response(response: str, fallback_title: str = "Untitled Story") -> Tuple[str, str, str]:
    text = response or ""

    title_match = re.search(r"(?:TITLE|Title)\s*:?\s*(.*?)(?=\n|$)", text, re.IGNORECASE)
    moral_match = re.search(r"(?:MORAL|Moral)\s*:?\s*(.*?)$", text, re.IGNORECASE | re.DOTALL)
    story_match = re.search(
        r"(?:STORY|Story)\s*:?\s*([\s\S]*?)(?=(?:MORAL|Moral)\s*:|$)",
        text,
        re.IGNORECASE,
    )

    title = title_match.group(1).strip() if title_match and title_match.group(1).strip() else fallback_title
    moral = moral_match.group(1).strip() if moral_match else ""

    if story_match and story_match.group(1).strip():
        content = story_match.group(1).strip()
    else:
        content = text
        if title_match:
            content = content.replace(title_match.group(0), "")
        if moral_match:
            content = content.replace(moral_match.group(0), "")
        content = content.strip()

    content = re.sub(r"^(?:STORY|Story)\s*:?\s*", "", content, flags=re.IGNORECASE).strip()
    return title, content, moral


def generate_story(request: StoryRequest, improvement_context: Optional[str] = None) -> Story:
    system_prompt = get_storyteller_system_prompt(request.category)

    prompt = f"""Create a bedtime story with these elements:
- Characters: {', '.join(request.characters) if request.characters else 'Create appropriate characters'}
- Themes: {', '.join(request.themes) if request.themes else 'friendship and kindness'}
- Setting: {request.setting}
- Tone: {request.tone}
- Original request: "{request.raw_input}"
"""
    if improvement_context:
        prompt += f"\n\nIncorporate these improvement notes from prior judging:\n{improvement_context}\n"

    response = call_model(prompt, system_prompt, max_tokens=STORY_MAX_TOKENS, temperature=0.8)
    title, content, moral = parse_story_response(response, fallback_title="Untitled Story")

    return Story(title=title, content=content, moral=moral, version=1)


# LLM Judge

JUDGE_SYSTEM_PROMPT = """You are a careful children's literature critic.

SCORING RULES:
- Round 1: Be critical. Cap scores at 6/10 unless perfection.
- Round 2+: REWARD IMPROVEMENT. If the story fixed previous issues, the score MUST go up.
- Be honest. If it got worse, lower the score.

EVALUATION CRITERIA (1-10):
1. AGE_APPROPRIATENESS (Vocabulary suitable for 5-10?)
2. ENGAGEMENT (Is it boring?)
3. MORAL_CLARITY (Is the lesson clear?)
4. STORY_STRUCTURE (Beginning, Middle, End?)
5. LANGUAGE_QUALITY (Vivid descriptions?)

IMPORTANT FORMATTING:
- Your FEEDBACK section must be a single paragraph summary.
- Do NOT list the scores again inside the FEEDBACK section.
- Put detailed bullet points ONLY in the SUGGESTIONS section.

Respond in this exact format:
OVERALL_SCORE: [1-10]
AGE_APPROPRIATENESS: [1-10]
ENGAGEMENT: [1-10]
MORAL_CLARITY: [1-10]
STORY_STRUCTURE: [1-10]
LANGUAGE_QUALITY: [1-10]
FEEDBACK: [2-3 sentences summarizing the critique. Do not repeat scores here.]
SUGGESTIONS:
- [bullet 1]
- [bullet 2]
"""


def parse_judge_response(response: str) -> JudgeFeedback:
    text = response or ""

    def find_score(pattern: str, default: int) -> int:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return default
        return clamp_int(m.group(1), 1, 10, default)

    overall = find_score(r"(?:OVERALL[_\s]?SCORE|Overall Score)\s*:?\s*(\d+)", 5)
    age = find_score(r"(?:AGE[_\s]?APPROPRIATENESS|Age Appropriateness)\s*:?\s*(\d+)", 5)
    eng = find_score(r"(?:ENGAGEMENT|Engagement)\s*:?\s*(\d+)", 5)
    moral = find_score(r"(?:MORAL[_\s]?CLARITY|Moral Clarity)\s*:?\s*(\d+)", 5)
    struct = find_score(r"(?:STORY[_\s]?STRUCTURE|Story Structure)\s*:?\s*(\d+)", 5)
    lang = find_score(r"(?:LANGUAGE[_\s]?QUALITY|Language Quality)\s*:?\s*(\d+)", 5)

    feedback_match = re.search(
        r"(?:FEEDBACK|Feedback)\s*:?\s*(.*?)(?=(?:SUGGESTIONS|Suggestions)\s*:|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    feedback = feedback_match.group(1).strip() if feedback_match else ""

    suggestions: List[str] = []
    suggestions_match = re.search(r"(?:SUGGESTIONS|Suggestions)\s*:?\s*(.*?)$", text, re.IGNORECASE | re.DOTALL)
    if suggestions_match:
        suggestions_text = suggestions_match.group(1).strip()
        bullet_lines = re.findall(r"[-•*]\s*(.+)", suggestions_text)
        suggestions = [s.strip() for s in bullet_lines if s.strip()]
        if not suggestions and suggestions_text:
            suggestions = [suggestions_text]

    return JudgeFeedback(
        overall_score=overall,
        age_appropriateness=age,
        engagement=eng,
        moral_clarity=moral,
        story_structure=struct,
        language_quality=lang,
        feedback=feedback,
        suggestions=suggestions,
    )


def judge_story(
    story: Story,
    request: StoryRequest,
    round_num: int = 1,
    history: Optional[List[JudgeFeedback]] = None,
) -> JudgeFeedback:
    history = history or []

    round_context = ""
    if round_num == 1:
        round_context = "This is a first draft. Be extremely critical. Do not give a score higher than 6 unless it is a masterpiece."
    elif round_num > 1:
        round_context = f"This is revision #{round_num}. Check if they fixed the previous issues. You can raise the score if they did."

    if history:
        prior = "\n".join(format_feedback_for_context(history[i], i + 1) for i in range(len(history)))
        previous_context = f"PRIOR FEEDBACK:\n{prior}\n"
    else:
        previous_context = ""

    system_prompt = JUDGE_SYSTEM_PROMPT 

    prompt = f"""Evaluate this draft (Round {round_num}):

REQUEST: "{request.raw_input}"
CATEGORY: {request.category.value}
TONE: {request.tone}

STORY:
{format_story_for_context(story)}

CONTEXT:
{round_context}
{previous_context}
"""

    response = call_model(prompt, system_prompt, max_tokens=JUDGE_MAX_TOKENS, temperature=0.4)
    return parse_judge_response(response)


# Story Refinement

def build_improvement_context(history: List[JudgeFeedback]) -> str:
    if not history:
        return ""
    latest = history[-1]
    suggestions_text = "\n".join(f"- {s}" for s in latest.suggestions) if latest.suggestions else "- Improve overall clarity and engagement."
    return (
        f"Latest judge scores: overall {latest.overall_score}/10 "
        f"(age {latest.age_appropriateness}, engagement {latest.engagement}, moral {latest.moral_clarity}, "
        f"structure {latest.story_structure}, language {latest.language_quality}).\n"
        f"Latest feedback: {latest.feedback}\n"
        f"Concrete suggestions:\n{suggestions_text}"
    )


def refine_story(story: Story, request: StoryRequest, history: List[JudgeFeedback]) -> Story:
    system_prompt = get_storyteller_system_prompt(request.category)

    improvement_context = build_improvement_context(history)

    prompt = f"""Revise this children's story using the judge's critique.

GOALS:
- Keep it suitable for ages 5-10
- Match the requested category, tone, and setting
- Keep the moral positive and not preachy
- Improve weak areas called out by the judge

REQUEST DETAILS:
- Category: {request.category.value}
- Tone: {request.tone}
- Setting: {request.setting}

CURRENT STORY:
{format_story_for_context(story)}

IMPROVEMENT NOTES:
{improvement_context}

Return the full revised story in this format:
TITLE: [Title]
STORY:
[Full story]
MORAL: [Moral]
"""

    response = call_model(prompt, system_prompt, max_tokens=STORY_MAX_TOKENS, temperature=0.7)
    title, content, moral = parse_story_response(response, fallback_title=story.title)

    return Story(title=title, content=content, moral=moral, version=story.version + 1)


# User Feedback and Modification

def get_user_modification_prompt(user_feedback: str, story: Story, request: StoryRequest) -> str:
    return f"""The user wants changes to this story.

REQUEST DETAILS:
- Category: {request.category.value}
- Tone: {request.tone}
- Setting: {request.setting}

CURRENT STORY:
{format_story_for_context(story)}

USER'S REQUEST: "{user_feedback}"

Please modify the story to incorporate the user's feedback while maintaining:
- Age-appropriate content (5-10 years)
- A clear story arc (opening, challenge, climax, resolution)
- A positive moral lesson
- The requested category, tone, and setting

Format your response as:
TITLE: [Title]
STORY:
[Full modified story]
MORAL: [Moral]
"""


def apply_user_modification(story: Story, request: StoryRequest, modification: str) -> Story:
    prompt = get_user_modification_prompt(modification, story, request)
    system_prompt = get_storyteller_system_prompt(request.category)

    response = call_model(prompt, system_prompt, max_tokens=STORY_MAX_TOKENS, temperature=0.7)
    title, content, moral = parse_story_response(response, fallback_title=story.title)
    return Story(title=title, content=content, moral=moral, version=story.version + 1)


# Interactive Choice Mode (Micro Choose-Your-Own-Adventure)

CHOICE_PROPOSER_SYSTEM_PROMPT = """You help create interactive bedtime stories for children ages 5-10.
Given the story so far, propose EXACTLY two safe, child-friendly options for what could happen next.

RULES:
- No violence, gore, self-harm, abuse, hate, or sexual content
- Avoid scary elements (no monsters that harm, no kidnapping, no realistic danger)
- Keep each option to ONE short sentence
- Options should be meaningfully different

OUTPUT FORMAT (exactly two lines):
CHOICE_1: ...
CHOICE_2: ...
"""

def parse_choice_proposal(text: str) -> Tuple[str, str]:
    c1_match = re.search(r"CHOICE_1\s*:\s*(.+)", text or "", re.IGNORECASE)
    c2_match = re.search(r"CHOICE_2\s*:\s*(.+)", text or "", re.IGNORECASE)
    c1 = (c1_match.group(1).strip() if c1_match else "")
    c2 = (c2_match.group(1).strip() if c2_match else "")

    # Fallback: try numbered lines
    if not c1 or not c2:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        numbered = [re.sub(r"^\s*[12][\)\.]\s*", "", ln).strip() for ln in lines if re.match(r"^\s*[12][\)\.]\s*", ln)]
        if len(numbered) >= 2:
            c1, c2 = numbered[0], numbered[1]

    # Last-resort defaults
    if not c1:
        c1 = "Follow a trail of twinkling lights to see where it leads."
    if not c2:
        c2 = "Ask a friendly neighbor for help and a cozy hint."

    return c1, c2


def propose_next_choices(story: Story, request: StoryRequest, step_num: int, total_steps: int) -> Tuple[str, str]:
    prompt = f"""Propose two next-step options.

CONTEXT:
- Interactive step: {step_num} of {total_steps}
- Requested category: {request.category.value}
- Tone: {request.tone}
- Setting: {request.setting}

STORY SO FAR:
{format_story_for_context(story)}
"""

    resp = call_model(
        prompt=prompt,
        system_prompt=CHOICE_PROPOSER_SYSTEM_PROMPT,
        max_tokens=CHOICE_PROPOSAL_MAX_TOKENS,
        temperature=0.5,
    )
    return parse_choice_proposal(resp)


def parse_continuation_response(text: str) -> Tuple[str, str]:
    """Returns (continuation_text, moral_or_empty)."""
    t = text or ""

    cont_match = re.search(
        r"(?:CONTINUATION)\s*:?(.*?)(?=(?:MORAL)\s*:|$)",
        t,
        re.IGNORECASE | re.DOTALL,
    )
    moral_match = re.search(r"(?:MORAL)\s*:?(.*)$", t, re.IGNORECASE | re.DOTALL)

    continuation = cont_match.group(1).strip() if cont_match and cont_match.group(1).strip() else t.strip()
    continuation = re.sub(r"^CONTINUATION\s*:?", "", continuation, flags=re.IGNORECASE).strip()
    moral = moral_match.group(1).strip() if moral_match else ""

    return continuation, moral


def generate_continuation(story: Story, request: StoryRequest, chosen_option: str, step_num: int, total_steps: int) -> Tuple[str, str]:
    is_final = step_num >= total_steps

    system_prompt = get_storyteller_system_prompt(request.category)

    prompt = f"""Continue the bedtime story in an interactive way.

STORY SO FAR:
{format_story_for_context(story)}

USER CHOSEN OPTION:
{chosen_option}

CONSTRAINTS:
- Ages 5-10, safe and not scary
- Keep it consistent with the setting and tone
- Write 120-200 words
- Continue smoothly from the last sentence
"""

    if is_final:
        prompt += """
FINAL STEP:
- Resolve the story with a satisfying, cozy ending
- Include a short calming closing that feels bedtime-ready
- Output a MORAL in one sentence

OUTPUT FORMAT:
CONTINUATION:
[continuation text]
MORAL: [one sentence]
"""
    else:
        prompt += """
NOT FINAL YET:
- End with a gentle, curious moment (not scary) that invites the next choice
- Do NOT include a moral yet

OUTPUT FORMAT:
CONTINUATION:
[continuation text]
"""

    resp = call_model(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=CHOICE_CONTINUATION_MAX_TOKENS,
        temperature=0.8,
    )

    return parse_continuation_response(resp)


def run_interactive_choice_mode(story: Story, request: StoryRequest, total_steps: int = CHOICE_MODE_MAX_STEPS) -> Story:
    """Adds up to `total_steps` interactive continuation beats to the story."""
    current = story

    print("\n" + "=" * 60)
    print("Interactive Choice Mode")
    print("Pick 1 or 2 at each step. Type 'quit' to exit this mode.")
    print("=" * 60 + "\n")

    for step in range(1, total_steps + 1):
        c1, c2 = propose_next_choices(current, request, step_num=step, total_steps=total_steps)

        print(f"Step {step}/{total_steps} choices:")
        print(f"  [1] {c1}")
        print(f"  [2] {c2}")

        while True:
            pick = input("\nYour choice (1/2 or 'quit'): ").strip().lower()
            if pick in {"quit", "q", "exit"}:
                print("\nExiting Interactive Choice Mode.\n")
                return current
            if pick in {"1", "2"}:
                break
            print("Please enter 1, 2, or 'quit'.")

        chosen = c1 if pick == "1" else c2
        continuation, maybe_moral = generate_continuation(current, request, chosen, step_num=step, total_steps=total_steps)

        # Append continuation to story
        new_content = (current.content.rstrip() + "\n\n" + continuation.strip()).strip()
        new_moral = maybe_moral.strip() or current.moral

        current = Story(
            title=current.title,
            content=new_content,
            moral=new_moral,
            version=current.version + 1,
        )

        print("\n" + "-" * 60)
        print("Continuation:")
        print(continuation.strip())
        if maybe_moral.strip():
            print("\n" + "-" * 60)
            print(f"Moral: {maybe_moral.strip()}")
        print("-" * 60 + "\n")

        if maybe_moral.strip():
            # Final step produced a moral, so we can stop early.
            break

    print("\nInteractive Choice Mode complete.\n")
    return current


# Display and Output Functions

def display_story(story: Story):
    print("\n" + "=" * 60)
    print(story.title)
    print("=" * 60 + "\n")
    print(story.content)
    print("\n" + "-" * 60)
    print(f"Moral: {story.moral}")
    print("=" * 60 + "\n")


def display_judge_feedback(feedback: JudgeFeedback, show_details: bool = False):
    print(f"\nJudge Score: {feedback.overall_score}/10")
    if show_details:
        print(f"   Age Appropriateness: {feedback.age_appropriateness}/10")
        print(f"   Engagement: {feedback.engagement}/10")
        print(f"   Moral Clarity: {feedback.moral_clarity}/10")
        print(f"   Story Structure: {feedback.story_structure}/10")
        print(f"   Language Quality: {feedback.language_quality}/10")
        if feedback.feedback:
            print(f"\n   {feedback.feedback}")
        if feedback.suggestions:
            print("\n   Suggestions:")
            for s in feedback.suggestions[:6]:
                print(f"    - {s}")


def speak_story(story: Story, speed: float = 0.3):
    print("\n" + "=" * 60)
    print("Bedtime Reading Mode Activated...")
    print("=" * 60 + "\n")

    print("")
    for char in story.title:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.05)
    print("\n")
    time.sleep(0.5)

    for word in story.content.split():
        sys.stdout.write(word + " ")
        sys.stdout.flush()
        time.sleep(speed)
        if word.endswith((".", "!", "?")):
            time.sleep(speed * 2)

    print("\n\n" + "-" * 60)
    time.sleep(0.5)

    print("Moral: ", end="")
    for word in story.moral.split():
        sys.stdout.write(word + " ")
        sys.stdout.flush()
        time.sleep(speed)

    print("\n" + "=" * 60)
    time.sleep(1)
    print("\nThe End. Sweet dreams...\n")
    time.sleep(1)


# Story Generation Pipeline

def build_request_from_user_choices(user_input: str, category: StoryCategory, tone: str, setting: str) -> StoryRequest:
    analyzed = analyze_request(user_input)

    analyzed.category = category
    analyzed.tone = normalize_tone(tone)
    analyzed.setting = setting.strip() or analyzed.setting

    return analyzed


def generate_and_refine_story(request: StoryRequest, verbose: bool = True) -> Tuple[Story, List[JudgeFeedback]]:
    if verbose:
        print("\nStory request details:")
        print(f"   Category: {request.category.value}")
        print(f"   Tone: {request.tone}")
        print(f"   Setting: {request.setting}")
        if request.characters:
            print(f"   Characters: {', '.join(request.characters)}")
        if request.themes:
            print(f"   Themes: {', '.join(request.themes)}")

    if verbose:
        print("\nCrafting your story...")
    story = generate_story(request)

    history: List[JudgeFeedback] = []
    for iteration in range(MAX_REFINEMENT_ITERATIONS):
        round_num = iteration + 1
        if verbose:
            print(f"\nJudge reviewing story (round {round_num})...")

        feedback = judge_story(story, request, round_num=round_num, history=history)
        history.append(feedback)

        display_judge_feedback(feedback, show_details=verbose)

        if feedback.overall_score >= JUDGE_THRESHOLD:
            if verbose:
                print(f"   Reached threshold ({JUDGE_THRESHOLD}/10). Stopping early.")
            break

        if iteration < MAX_REFINEMENT_ITERATIONS - 1:
            if verbose:
                print("   Refining story based on feedback...")
            story = refine_story(story, request, history)
        else:
            if verbose:
                print("   Story refinement complete (max rounds reached).")

    return story, history


# Main Interactive Loop

def main():
    print("\n" + "=" * 60)
    print("BEDTIME STORY GENERATOR")
    print("For children ages 5-10")
    print("=" * 60)
    print("\nType 'quit' at any time to exit.\n")

    while True:
        user_input = input("What is your story idea? (e.g., 'a brave dragon', 'a lost teddy bear'): ").strip()

        if user_input.lower() in ["quit", "exit", "q"]:
            print("\nSweet dreams! Goodnight!\n")
            break

        if not user_input:
            print("Please tell me your story idea!\n")
            continue

        print("\nChoose a story category:")
        print("  [1] Adventure - Exciting discoveries and brave choices")
        print("  [2] Fantasy - Magic, talking animals, enchanted objects")
        print("  [3] Animal - Stories about animals with relatable personalities")
        print("  [4] Friendship - Cooperation, sharing, and kindness")
        print("  [5] Bedtime - Calm, soothing stories perfect for sleep")
        print("  [6] Educational - Learning woven into the story")
        print("  [7] Funny - Silly situations and gentle humor")

        category_choice = input("\nCategory (1-7): ").strip()
        category_map = {
            "1": StoryCategory.ADVENTURE,
            "2": StoryCategory.FANTASY,
            "3": StoryCategory.ANIMAL,
            "4": StoryCategory.FRIENDSHIP,
            "5": StoryCategory.BEDTIME,
            "6": StoryCategory.EDUCATIONAL,
            "7": StoryCategory.FUNNY,
        }
        category = category_map.get(category_choice, StoryCategory.BEDTIME)

        print("\nChoose the story tone:")
        print("  [1] Whimsical - Light, playful, and magical")
        print("  [2] Exciting - Adventurous and energetic")
        print("  [3] Calming - Peaceful and soothing")
        print("  [4] Humorous - Funny and silly")
        print("  [5] Heartwarming - Touching and emotional")
        print("  [6] Inspiring - Uplifting and motivational")

        tone_choice = input("\nTone (1-6): ").strip()
        tone_map = {
            "1": "whimsical",
            "2": "exciting",
            "3": "calming",
            "4": "humorous",
            "5": "heartwarming",
            "6": "inspiring",
        }
        tone = tone_map.get(tone_choice, "whimsical")

        print("\nChoose the story setting:")
        print("  [1] Magical forest - Enchanted woods with talking trees")
        print("  [2] Under the sea - Ocean depths with colorful sea creatures")
        print("  [3] Cozy village - A friendly neighborhood")
        print("  [4] Outer space - Stars, planets, and friendly aliens")
        print("  [5] Farm - Barns, fields, and farm animals")
        print("  [6] Castle - Royal kingdoms and brave knights")
        print("  [7] Jungle - Tropical wilderness with exotic animals")
        print("  [8] Arctic - Snowy landscapes with polar animals")
        print("  [9] Child's bedroom - Toys and imagination come alive")

        setting_choice = input("\nSetting (1-9): ").strip()
        setting_map = {
            "1": "a magical forest with enchanted trees",
            "2": "under the sea with colorful coral reefs",
            "3": "a cozy village where everyone is friendly",
            "4": "outer space among twinkling stars and friendly planets",
            "5": "a sunny farm with happy animals",
            "6": "a grand castle in a peaceful kingdom",
            "7": "a lush jungle full of wonder",
            "8": "the snowy Arctic with playful polar animals",
            "9": "a child's bedroom where toys come to life",
        }
        setting = setting_map.get(setting_choice, "a magical land")

        try:
            request = build_request_from_user_choices(user_input, category, tone, setting)
        except Exception as e:
            print(f"\nError analyzing request: {e}")
            print("Continuing with a simple fallback request.\n")
            request = StoryRequest(
                raw_input=user_input,
                category=category,
                characters=[],
                themes=[],
                setting=setting,
                tone=normalize_tone(tone),
            )

        print("\n" + "-" * 60)
        print("Generating your story:")
        print(f"  Idea: {user_input}")
        print(f"  Category: {request.category.value}")
        print(f"  Tone: {request.tone}")
        print(f"  Setting: {request.setting}")
        if request.characters:
            print(f"  Characters: {', '.join(request.characters)}")
        if request.themes:
            print(f"  Themes: {', '.join(request.themes)}")
        print("-" * 60)

        try:
            story, history = generate_and_refine_story(request, verbose=True)
        except Exception as e:
            print(f"\nError generating story: {e}\n")
            continue

        display_story(story)

        while True:
            print("Would you like to:")
            print("  [1] Finish (optionally save this story)")
            print("  [2] Listen in Bedtime Reading Mode (slow narration)")
            print("  [3] Request changes to this story")
            print("  [4] Generate a completely new version of this story (same idea)")
            print("  [5] Start over with a different story idea")
            print("  [6] Continue with Interactive Choice Mode (pick what happens next)")

            choice = input("\nYour choice (1-6): ").strip()

            if choice == "1":
                save_choice = input("\nWould you like to save this story to a file? (y/n): ").strip().lower()
                if save_choice in ["y", "yes"]:
                    safe_title = re.sub(r"[^\w\s-]", "", story.title).strip().replace(" ", "_")
                    filename = f"{safe_title}.txt" if safe_title else "story.txt"
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            f.write("=" * 60 + "\n")
                            f.write(f"{story.title}\n")
                            f.write("=" * 60 + "\n\n")
                            f.write(story.content + "\n\n")
                            f.write("-" * 60 + "\n")
                            f.write(f"Moral: {story.moral}\n")
                            f.write("=" * 60 + "\n")
                        print(f"\nStory saved to: {filename}")
                    except Exception as e:
                        print(f"\nError saving file: {e}")

                print("\nEnjoy the story! Sweet dreams!\n")
                return

            if choice == "2":
                print("\nEntering Bedtime Reading Mode...")
                print("(Press Ctrl+C to skip ahead if needed)\n")
                time.sleep(1)
                try:
                    speak_story(story, speed=0.3)
                except KeyboardInterrupt:
                    print("\n\nSkipped to the end!\n")
                print("\nSweet dreams!\n")
                break

            if choice == "6":
                try:
                    story = run_interactive_choice_mode(story, request, total_steps=CHOICE_MODE_MAX_STEPS)
                    display_story(story)

                    # After Interactive Choice Mode, automatically save and finish.
                    safe_title = re.sub(r"[^\w\s-]", "", story.title).strip().replace(" ", "_")
                    filename = f"{safe_title}.txt" if safe_title else "story.txt"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write("=" * 60 + "\n")
                        f.write(f"{story.title}\n")
                        f.write("=" * 60 + "\n\n")
                        f.write(story.content + "\n\n")
                        f.write("-" * 60 + "\n")
                        f.write(f"Moral: {story.moral}\n")
                        f.write("=" * 60 + "\n")

                    print(f"\nStory saved to: {filename}")
                    print("\nEnjoy the story! Sweet dreams!\n")
                    return
                except Exception as e:
                    print(f"\nError during Interactive Choice Mode or saving: {e}\n")
                continue

            if choice == "3":
                modification = input("\nWhat changes would you like? ").strip()
                if modification:
                    try:
                        story = apply_user_modification(story, request, modification)
                        display_story(story)
                    except Exception as e:
                        print(f"\nError applying changes: {e}\n")
                continue

            if choice == "4":
                print("\nGenerating a fresh story with the same request...")
                try:
                    story, history = generate_and_refine_story(request, verbose=True)
                    display_story(story)
                except Exception as e:
                    print(f"\nError generating new version: {e}\n")
                continue

            if choice == "5":
                break

            print("Please enter 1, 2, 3, 4, 5, or 6.\n")


# Entry Point

if __name__ == "__main__":
    main()