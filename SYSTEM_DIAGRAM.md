# System Architecture Block Diagram

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                         │
│  (Input request + Menu choices: Category, Tone, Setting)        │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│              REQUEST ANALYZER (Stage 1)                         │
│  Input: Raw user request                                        │
│  LLM: gpt-3.5-turbo (0.2 temp, 500 tokens)                      │
│  Output: Structured StoryRequest                                │
│  • Category (7 options)                                         │
│  • Characters (list)                                            │
│  • Themes (list)                                                │
│  • Setting                                                      │
│  • Tone (6 options)                                             │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│             STORYTELLER (Stage 2 - Initial Draft)               │
│  Input: StoryRequest (category, characters, themes, etc.)       │
│  LLM: gpt-3.5-turbo (0.8 temp, 2000 tokens)                     │
│  System Prompt: Category-specific (7 variants)                  │
│  Output: Story (Title, Content, Moral, Version=1)               │
│  Features:                                                      │
│  • Story arc structure (opening→climax→resolution)              │
│  • 400-600 words                                                │
│  • Age-appropriate for 5-10 years                               │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      │ Story Version 1
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│        QUALITY ASSURANCE LOOP (Up to 5 iterations)              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  JUDGE (Evaluation Stage)                                │   │
│  │  Input: Story + Request + Prior feedback history         │   │
│  │  LLM: gpt-3.5-turbo (0.4 temp, 900 tokens)               │   │
│  │  System Prompt: Strict critique with round awareness     │   │
│  │  Output: JudgeFeedback                                   │   │
│  │  • Overall Score (1-10)                                  │   │
│  │  • 5 Criteria Scores:                                    │   │
│  │    - Age Appropriateness                                 │   │
│  │    - Engagement                                          │   │
│  │    - Moral Clarity                                       │   │
│  │    - Story Structure                                     │   │
│  │    - Language Quality                                    │   │
│  │  • Feedback (narrative critique)                         │   │
│  │  • Suggestions (actionable bullet points)                │   │
│  │                                                          │   │
│  │  Strictness Strategy:                                    │   │
│  │  • Round 1: Cap at 6/10 (very critical)                  │   │
│  │  • Round 2+: Reward genuine improvements when fixed      │   │
│  │  • Early stop: If score >= 7/10, exit loop               │   │
│  │  • Max 5 rounds total (judge → refine → judge ...)       │   │
│  └──────────┬────────────────────────────────────────────── ┘   │
│             │                                                   │
│             ▼                                                   │
│        Score >= 7/10 ?                                          │
│         /           \                                           │
│       YES             NO (and iteration < 5)                    │
│       │                    │                                    │
│       │                    ▼                                    │
│       │        ┌─────────────────────────────────────────┐      │
│       │        │  REFINER (Improvement Stage)            │      │
│       │        │  Input: Story + Judge Feedback          │      │
│       │        │  LLM: gpt-3.5-turbo (0.7 temp)          │      │
│       │        │  Improves: Weak areas from judge        │      │
│       │        │  Output: Story (Version += 1)           │      │
│       │        │  Loop back to Judge →                   │      │
│       │        └─────────────────────────────────────────┘      │
│       │                    │                                    │
│       └────────┬───────────┘                                    │
│                ▼                                                │
│        Loop Complete                                            │
│        (Final Story + Feedback History)                         │
│                                                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      │ Final Story + Judge History
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│             DISPLAY & USER OPTIONS                              │
│  Present: Story + Judge Feedback                                │
│  User can choose one of 5 options:                              │
│                                                                 │
│  [1] SAVE TO FILE                                               │
│      └─> Creates safe filename + writes to disk                 │
│                                                                 │
│  [2] BEDTIME READING MODE                                       │
│      └─> Slow narration (0.3s/word) with story title            │
│          Creates immersive, sleepy experience                   │
│          Pauses at punctuation for effect                       │
│                                                                 │
│  [3] REQUEST MODIFICATION                                       │
│      └─> User provides feedback                                 │
│          └─> MODIFIER (LLM applies changes)                     │
│              └─> Display modified story                         │
│                                                                 │
│  [4] REGENERATE                                                 │ 
│      └─> Restart from step "Storyteller" with same request      │
│          (New judge/refine cycle)                               │
│                                                                 │
│  [5] START FRESH                                                │
│      └─> Return to main menu (new user input)                   │
│                                                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ├─> [1] Save → Exit
                      │
                      ├─> [2] Read → Back to Menu
                      │
                      ├─> [3] Modify ─┐
                      │               ▼
                      │        MODIFIER (LLM)
                      │        Applies user changes
                      │        Returns modified story
                      │               │
                      │               ▼
                      │        Back to User Options
                      │
                      ├─> [4] Regenerate ─┐
                      │                   ▼
                      │            New Story Generation
                      │            (Judge/Refine Loop)
                      │                   │
                      │                   ▼
                      │            Back to Display
                      │
                      └─> [5] Start Fresh
                          └─> Back to main()
```

## Component Interaction Matrix

| Component | Input | LLM Call | Output | Temperature |
|-----------|-------|----------|--------|-------------|
| **Analyzer** | Raw user request | gpt-3.5-turbo | StoryRequest (characters/themes + suggested defaults; menu overrides category/tone/setting) | 0.2 (deterministic) |
| **Storyteller** | StoryRequest (initial draft) | gpt-3.5-turbo | Story (title, content, moral) | 0.8 (creative) |
| **Judge** | Story + StoryRequest + judge history | gpt-3.5-turbo | JudgeFeedback (scores, feedback, suggestions) | 0.4 (consistent) |
| **Refiner** | Story + JudgeFeedback | gpt-3.5-turbo | Story v2+ (improvements) | 0.7 (balanced) |
| **Modifier** | Story + user modification request | gpt-3.5-turbo | Story v2+ (user changes) | 0.7 (balanced) |

## Data Flow - Example Journey

```
User Input: "I want a funny story about a cat"
Menu Choices:
    - Category: Funny
    - Tone: Humorous
    - Setting: A cozy village where everyone is friendly
    │
    ▼
ANALYZER
    ├─ Extracts CHARACTERS → ["cat", "new friends inferred"]
    ├─ Extracts THEMES → ["humor", "friendship"]
    └─ Suggests defaults if missing (menu choices still take precedence)
    │
    ▼
STORYTELLER (v1)
    └─ Creates a 400-600 word funny cat story matching the menu choices
    │
    ▼
JUDGE ROUND 1
    ├─ Score: 5/10 (strict on first draft)
    ├─ Feedback: "Good humor but weak structure"
    └─ Suggestions: [improve climax, add more dialogue, ...]
    │
    ├─ 5/10 < 7/10 and round < 5, so refine
    │
    ▼
REFINER
    ├─ Incorporates judge suggestions
    └─ Story v2 output
    │
    ▼
JUDGE ROUND 2
    ├─ Score: 6/10 (improvement detected)
    └─ Suggestions: [tighten ending, strengthen moral, ...]
    │
    ├─ 6/10 < 7/10 and round < 5, so refine
    │
    ▼
REFINER
    └─ Story v3 output
    │
    ▼
JUDGE ROUND 3
    ├─ Score: 7/10 (threshold reached)
    └─ [EARLY STOP]
    │
    ▼
DISPLAY
    ├─ Show final story (v3)
    ├─ Show judge feedback history
    └─ Offer 5 user options
```

## Key Design Decisions

1. **Strict Judge Strategy**: Round 1 caps at 6/10 (unless exceptional), later rounds reward genuine fixes  
2. **Up to 5 Rounds**: Run at most 5 judge/refine rounds with early stopping at the quality threshold  
3. **Early Stop at 7/10**: Stops refinement once the target quality score is reached  
4. **Temperature Tuning**:  
   - Analyzer (0.2): Consistent extraction  
   - Storyteller (0.8): Creative, varied stories  
   - Judge (0.4): Reliable, stable evaluations  
   - Refiner (0.7): Balanced improvement  
5. **Token Management**: Story (2000), Judge (900), Analyzer (500) to maintain quality  
6. **Regex-Based Parsing**: Handles GPT-3.5's inconsistent formatting (TITLE/Title/title:)  
7. **User Control Loop**: 5 post-story options for full agency (save, listen, modify, regenerate, restart)  
8. **Bedtime Reading Mode**: 0.3s/word narration creates immersive, slow-paced experience  

## Error Handling

```
All LLM calls wrapped in retry logic:
    ├─ 3 total attempts
    ├─ Exponential backoff (1.5s base)
    └─ Raise a clear error if all retries fail (main loop catches it)

File operations:
    ├─ Safe filename handling (remove special chars)
    └─ Try-catch on write operations

Parsing:
    ├─ Regex extraction with multiple format variants
    └─ Sensible defaults if parsing fails
```

## System Features

✓ **7 Story Categories** with specialized prompts (Adventure, Fantasy, Animal, Friendship, Bedtime, Educational, Funny)  
✓ **6 Tone Options** (Whimsical, Exciting, Calming, Humorous, Heartwarming, Inspiring)  
✓ **9 Setting Options** via user input variety  
✓ **5-Criteria Judge** (Age, Engagement, Moral, Structure, Language)  
✓ **Iterative Refinement** (up to 5 rounds, early stop at 7/10)  
✓ **User Feedback Loop** (save, listen, modify, regenerate, restart)  
✓ **Bedtime Reading Mode** (slow narration with pauses)  
✓ **Robust Error Handling** (retries, fallbacks, safe parsing)
