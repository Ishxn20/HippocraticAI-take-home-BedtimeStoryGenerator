# Magical Bedtime Story Generator 🌙

A children's bedtime story generator (ages 5-10) with LLM-based quality assurance.

## Quick Start

```bash
pip install -r requirements.txt

export OPENAI_API_KEY="your-api-key-here"

python main.py
```

## Features

- **7 Story Categories**: Adventure, Fantasy, Animal, Friendship, Bedtime, Educational, Funny
- **6 Tone Options**: Whimsical, Exciting, Calming, Humorous, Heartwarming, Inspiring
- **Guided Menu System**: 378 story combinations from category × tone × setting choices
- **5-Round Refinement**: Up to 5 rounds with early stop at 7/10
- **Auto-Improvement**: Judge feedback drives targeted story enhancements
- **User Feedback Loop**: Save, modify, regenerate, or start fresh
- **Story Arc Structure**: Classic narrative framework for engaging stories
- **Bedtime Reading Mode**: Slow narration that simulates reading aloud (surprise feature!)

## System Architecture

See [SYSTEM_DIAGRAM.md](SYSTEM_DIAGRAM.md) for the complete block diagram.

```
User
  │
  ▼
Menu choices (category, tone, setting) + free-text story idea
  │
  ▼
Request Analyzer (LLM) → extracts characters/themes (and defaults)
  │
  ▼
Storyteller (LLM) → draft story
  │
  ▼
Judge (LLM) → scores + feedback
  │
  ├─ if score >= 7: stop
  ▼
Refiner (LLM) → revised story
  │
  └─ loop back to Judge (up to 5 rounds total)
```

## How It Works

1. **Menu-Driven Input**: User selects category (7 options), tone (6 options), and setting via guided prompts  
2. **Request Analysis**: LLM extracts characters and themes (and suggests defaults). Menu choices override category, tone, and setting.  
3. **Story Generation**: Uses category-specific prompts (7 variants) with story arc structure  
4. **Strict Quality Evaluation**:  
   - Round 1: Judge is highly critical (caps scores at 6/10 unless exceptional)  
   - Rounds 2-5: Judge checks whether issues were fixed and rewards genuine improvements  
   - Early stop if story reaches the 7/10 threshold before round 5  
5. **Iterative Refinement**: Up to 5 judge-refine cycles ensure meaningful story improvements  
6. **User Interaction**: Save to file, listen in reading mode, modify, regenerate, or start fresh  

## Prompting Strategies Used

- **Role-based system prompts**: Specialized personas for analyzer, storyteller, and judge  
- **Structured output formatting**: Consistent parsing with TITLE/STORY/MORAL format  
- **Temperature tuning**: Analyzer (0.2), Storyteller (0.8), Judge (0.4), Refiner (0.7) for optimal performance  
- **Chain of evaluation**: Multi-criteria scoring (5 dimensions) with actionable suggestions  
- **Category specialization**: 7 distinct storytelling modes with tailored guidance  
- **Progressive refinement**: Up to 5 judge/refine rounds with early stopping at the quality threshold  
- **Regex-hardened parsing**: Handles GPT-3.5-turbo's inconsistent output formatting  

---

# Original Assignment

Welcome to the [Hippocratic AI](https://www.hippocraticai.com) coding assignment

## Instructions
The attached code is a simple python script skeleton. Your goal is to take any simple bedtime story request and use prompting to tell a story appropriate for ages 5 to 10.
- Incorporate a LLM judge to improve the quality of the story
- Provide a block diagram of the system you create that illustrates the flow of the prompts and the interaction between judge, storyteller, user, and any other components you add
- Do not change the openAI model that is being used. 
- Please use your own openAI key, but do not include it in your final submission.
- Otherwise, you may change any code you like or add any files

---

## Rules
- This assignment is open-ended
- You may use any resources you like with the following restrictions
   - They must be resources that would be available to you if you worked here (so no other humans, no closed AIs, no unlicensed code, etc.)
   - Allowed resources include but not limited to Stack overflow, random blogs, chatGPT et al
   - You have to be able to explain how the code works, even if chatGPT wrote it
- DO NOT PUSH THE API KEY TO GITHUB. OpenAI will automatically delete it

---

## What does "tell a story" mean?
It should be appropriate for ages 5-10. Other than that it's up to you. Here are some ideas to help get the brain-juices flowing!
- Use story arcs to tell better stories
- Allow the user to provide feedback or request changes
- Categorize the request and use a tailored generation strategy for each category

---

## How will I be evaluated
Good question. We want to know the following:
- The efficacy of the system you design to create a good story
- Are you comfortable using and writing a python script
- What kinds of prompting strategies and agent design strategies do you use
- Are the stories your tool creates good?
- Can you understand and deconstruct a problem
- Can you operate in an open-ended environment
- Can you surprise us

---

## Other FAQs
- How long should I spend on this? 
No more than 2-3 hours
- Can I change what the input is? 
Sure
- How long should the story be?
You decide