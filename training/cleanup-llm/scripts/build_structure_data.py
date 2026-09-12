#!/usr/bin/env python3
"""Stage 3b (LLM v1 structure): synthetic transcript->formatted pairs.

Covers source-grounded formatting only: spoken lists become bullets, dotted
bullets, or numbers; explicit labels become short titles; spoken names keep
capitalization; explicit emoji requests map to exactly that emoji. Negative
controls never invent items, titles, names, dates, or emoji.
"""

import json
import os
import random

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

SYSTEM_V1 = (
    "You are Vaani cleanup LLM v1, a source-grounded transcript formatter. "
    "Fix grammar, punctuation, capitalization, sentence boundaries, filler "
    "words, false starts, duplicates, and common spelling mistakes. Preserve "
    "intended content words, names, numbers, dates, quantities, units, code, "
    "paths, negation, profanity, pronouns, and the original language. Do not add, "
    "remove, reorder, translate, expand, summarize, or reinterpret content. "
    "Make a list only from items actually spoken: use '- ' by default, '• ' "
    "only when the speaker says dotted or dot bullets, and numbered lines "
    "only for a spoken sequence or order. Build a Markdown table only when "
    "the transcript gives explicit columns and rows; never invent cells. "
    "Add a short title only when the "
    "transcript explicitly provides one. A bare formatting command with no "
    "spoken items is prose, not a list. Treat a requested emoji as decoration; "
    "never make the emoji name itself a list item. Map an explicitly spoken emoji "
    "request to exactly that emoji and add no other emoji. If unsure, return "
    "the input unchanged."
)

PAIRS = [
    ("grocery list milk eggs bread and butter", "Grocery list:\n- Milk\n- Eggs\n- Bread\n- Butter"),
    ("make a grocery list apples bananas milk eggs and bread", "Grocery list:\n- Apples\n- Bananas\n- Milk\n- Eggs\n- Bread"),
    ("shopping list milk eggs and bread", "Shopping list:\n- Milk\n- Eggs\n- Bread"),
    ("add milk eggs and bread to my grocery list", "Grocery list:\n- Milk\n- Eggs\n- Bread"),
    ("weekly groceries rice lentils oil sugar and tea", "Weekly groceries:\n- Rice\n- Lentils\n- Oil\n- Sugar\n- Tea"),
    ("make a dotted list milk eggs and bread", "Grocery list:\n• Milk\n• Eggs\n• Bread"),
    ("dotted shopping list call mom and pay rent", "Shopping list:\n• Call mom\n• Pay rent"),
    ("bullet list milk and eggs", "Shopping list:\n- Milk\n- Eggs"),
    ("numbered shopping list first milk second eggs third bread", "Shopping list:\n1. Milk\n2. Eggs\n3. Bread"),
    ("grocery list with check mark emoji milk eggs and bread", "Grocery list:\n- ✅ Milk\n- ✅ Eggs\n- ✅ Bread"),
    ("remind me to call mom buy groceries and pay rent", "Reminders:\n- Call mom\n- Buy groceries\n- Pay rent"),
    ("tasks email priya finish the report and book tickets", "Tasks:\n- Email Priya\n- Finish the report\n- Book tickets"),
    ("meeting agenda first budget then hiring then launch date", "Meeting agenda:\n1. Budget\n2. Hiring\n3. Launch date"),
    ("three action items call the client send the invoice and schedule the demo", "Action items:\n1. Call the client\n2. Send the invoice\n3. Schedule the demo"),
    ("project steps design prototype test and launch", "Project steps:\n1. Design\n2. Prototype\n3. Test\n4. Launch"),
    ("packing list passport charger tickets and jacket", "Packing list:\n- Passport\n- Charger\n- Tickets\n- Jacket"),
    ("travel checklist book the flight reserve the hotel and pack the charger", "Travel checklist:\n- Book the flight\n- Reserve the hotel\n- Pack the charger"),
    ("there are three reasons first price second quality third support", "There are three reasons:\n1. Price\n2. Quality\n3. Support"),
    ("two reasons first location second price", "Two reasons:\n1. Location\n2. Price"),
    ("main points budget timeline and risks", "Main points:\n- Budget\n- Timeline\n- Risks"),
    ("first finish the report then call vishal then book the tickets", "Tasks:\n1. Finish the report\n2. Call Vishal\n3. Book the tickets"),
    ("agenda budget hiring and launch date", "Agenda:\n- Budget\n- Hiring\n- Launch date"),
    ("meeting notes budget timeline and risks", "Meeting notes:\n- Budget\n- Timeline\n- Risks"),
    ("birthday plan cake balloons and music", "Birthday plan:\n- Cake\n- Balloons\n- Music"),
    ("recipe flour sugar eggs and butter", "Recipe:\n- Flour\n- Sugar\n- Eggs\n- Butter"),
    ("workout warm up run and stretch", "Workout:\n- Warm up\n- Run\n- Stretch"),
    ("things to do call mom and pay rent", "Things to do:\n- Call mom\n- Pay rent"),
    ("groceries milk eggs and bread", "Groceries:\n- Milk\n- Eggs\n- Bread"),
    ("attendees vishal priya and rahul", "Attendees:\n- Vishal\n- Priya\n- Rahul"),
    ("team vishal priya and rahul", "Team:\n- Vishal\n- Priya\n- Rahul"),
    ("groceries for diya milk and bread", "Groceries for Diya:\n- Milk\n- Bread"),
    ("invite vishal priya and rahul", "- Vishal\n- Priya\n- Rahul"),
    ("buy milk eggs and bread", "- Milk\n- Eggs\n- Bread"),
    ("call mom buy groceries and pay rent", "- Call mom\n- Buy groceries\n- Pay rent"),
    ("step one install step two configure step three test", "1. Install\n2. Configure\n3. Test"),
    ("rank the options price first quality second", "Options:\n1. Price\n2. Quality"),
    ("call vishal sharma tomorrow at ten", "Call Vishal Sharma tomorrow at 10."),
    ("email priya patel about the report", "Email Priya Patel about the report."),
    ("meet rahul verma at five pm near mg road", "Meet Rahul Verma at 5 p.m. near MG Road."),
    ("my doctor anita desai said rest for two days", "My doctor, Anita Desai, said rest for two days."),
    ("my friend sara khan is coming on sunday", "My friend, Sara Khan, is coming on Sunday."),
    ("ask professor meera iyer for the notes", "Ask Professor Meera Iyer for the notes."),
    ("save arjun mehta phone number nine eight seven six five four three two one zero", "Save Arjun Mehta, phone number 9876543210."),
    ("order for kabir singh two coffees", "Order for Kabir Singh: two coffees."),
    ("birthday message for diya keep the exact wording", "Birthday message for Diya: keep the exact wording."),
    ("thanks with a smiley face emoji", "Thanks 😊."),
    ("thumbs up emoji", "👍"),
    ("add a party popper emoji after congratulations", "Congratulations 🎉."),
    ("meeting at ten with a calendar emoji", "Meeting at 10 📅."),
    ("urgent with a red exclamation emoji", "Urgent ❗"),
    ("well done team with a clapping hands emoji", "Well done, team 👏."),
    ("workout complete with a fire emoji", "Workout complete 🔥."),
    ("hmm not sure with a thinking face emoji", "Hmm, not sure 🤔."),
    ("meeting at ten tomorrow", "Meeting at 10 tomorrow."),
    ("i will defiantly be their tomorrow", "I will definitely be there tomorrow."),
    ("their going to come to they're house over there", "They are going to come to their house over there."),
    ("its raining and its very very cold", "It's raining, and it's very, very cold."),
    ("the meeting is on monday at ten a m", "The meeting is on Monday at 10 a.m."),
    ("i cant believe this is happening again today", "I can't. I can't believe this is happening again today."),
    ("genuine genuinely sorry about that", "Genuinely sorry about that."),
    ("no no don't go there", "No, no, don't go there."),
    ("i was so happy i mean really really happy", "I was so happy — I mean really, really happy!"),
    ("uh i went to the store um yesterday", "I went to the store yesterday."),
    ("i need i need milk uh eggs and bread", "I need:\n- Milk\n- Eggs\n- Bread"),
    ("i was i was going to call vishal yesterday", "I was going to call Vishal yesterday."),
    ("yesterday meeting cancelled reschedule friday", "Yesterday's meeting was cancelled; reschedule for Friday."),
    ("i went store i bought milk i came home", "I went to the store. I bought milk. I came home."),
    ("format these as pointers call mom and pay rent", "Pointers:\n- Call mom\n- Pay rent"),
    ("convert this into points price quality and support", "Points:\n- Price\n- Quality\n- Support"),
    ("make a grocery list with milk eggs and bread", "Grocery list:\n- Milk\n- Eggs\n- Bread"),
    ("doodh ande aur bread ki grocery list", "Grocery list:\n- Doodh\n- Ande\n- Bread"),
    ("hello this is me and i am testing the system and it should fix grammar when items are actually spoken", "Hello, this is me, and I am testing the system. It should fix grammar when items are actually spoken."),
    ("make a grocery list", "Make a grocery list."),
    ("make a list like a grocery list", "Make a list, like a grocery list."),
    ("turn this into pointers", "Turn this into pointers."),
    ("add milk to the list", "Add milk to the list."),
    ("i need things for the trip", "I need things for the trip."),
    ("agenda for tomorrow", "Agenda for tomorrow."),
    ("buy stuff", "Buy stuff."),
    ("there are a few reasons", "There are a few reasons."),
    ("tell me a grocery list", "Tell me a grocery list."),
    ("pros and cons flexible but expensive", "Pros and cons: flexible, but expensive."),
    ("the api key is abc one two three in slash home slash user slash config", "The API key is ABC123 in /home/user/config."),
    ("call mom at five pm on friday december twelfth", "Call Mom at 5 p.m. on Friday, December 12."),
    ("two coffees three teas and one black coffee", "Two coffees, three teas, and one black coffee."),
    ("send the file to vishal before noon", "Send the file to Vishal before noon."),
    ("please make a grocery list", "Please make a grocery list."),
    ("turn these into pointers", "Turn these into pointers."),
    ("format this as a list", "Format this as a list."),
    ("i want bullet points", "I want bullet points."),
    ("can you make it a numbered list", "Can you make it a numbered list?"),
    ("organize this into a grocery list", "Organize this into a grocery list."),
    ("make a dot list milk and eggs", "• Milk\n• Eggs"),
    ("dotted list apples and bananas", "• Apples\n• Bananas"),
    ("grocery list in dotted bullets milk and eggs", "Grocery list:\n• Milk\n• Eggs"),
    ("dot bullets call mom and pay rent", "• Call mom\n• Pay rent"),
    ("buy milk eggs and bread with a check mark emoji", "- ✅ Milk\n- ✅ Eggs\n- ✅ Bread"),
    ("thanks a lot with a folded hands emoji", "Thanks a lot 🙏."),
    ("good morning with a sun emoji", "Good morning ☀️."),
    ("happy birthday with a cake emoji", "Happy birthday 🎂."),
    ("call mom with a phone emoji", "Call Mom 📞."),
    ("urgent with a warning emoji", "Urgent ⚠️."),
    ("the emoji menu is open", "The emoji menu is open."),
    ("he said the word emoji", "He said the word emoji."),
    ("shopping list with check mark emoji apples and bananas", "Shopping list:\n- ✅ Apples\n- ✅ Bananas"),
    ("packing list with check mark emoji passport and charger", "Packing list:\n- ✅ Passport\n- ✅ Charger"),
    ("tasks with star emoji call mom and pay rent", "Tasks:\n- ⭐ Call mom\n- ⭐ Pay rent"),
    ("meeting notes with star emoji budget and timeline", "Meeting notes ⭐:\n- Budget\n- Timeline"),
    ("grocery list with check mark emoji", "Grocery list with check mark emoji."),
    ("add a check mark emoji after done", "Done ✅."),
    ("ask professor meera iyer for her notes", "Ask Professor Meera Iyer for her notes."),
    ("ask professor arjun mehta for his notes", "Ask Professor Arjun Mehta for his notes."),
    ("ask the manager for their notes", "Ask the manager for their notes."),
    ("she said she would bring her laptop", "She said she would bring her laptop."),
    ("he said he would bring his laptop", "He said he would bring his laptop."),
    ("grocery list item number one cake item number two eggs item number three milk", "Grocery list:\n1. Cake\n2. Eggs\n3. Milk"),
    ("items item number one passport size photo item number two vegetables", "Items:\n1. Passport-size photo\n2. Vegetables"),
    ("packing list item number one passport item number two charger item number three tickets", "Packing list:\n1. Passport\n2. Charger\n3. Tickets"),
    ("tasks item number one call mom item number two pay rent", "Tasks:\n1. Call Mom\n2. Pay rent"),
    ("laughing emoji", "😂"),
    ("it can create emojis laughing emoji", "It can create emojis 😂."),
    ("show me a laughing emoji", "😂"),
    ("testing emojis laughing emoji", "Testing emojis 😂."),
    ("this is a test of the new model i want a grocery list item number one cake item number two eggs", "This is a test of the new model. I want a grocery list:\n1. Cake\n2. Eggs"),
    ("for testing purposes make a shopping list item number one milk item number two bread item number three butter", "For testing purposes, make a shopping list:\n1. Milk\n2. Bread\n3. Butter"),
    ("reminders item number one call mom item number two pay rent item number three book tickets", "Reminders:\n1. Call Mom\n2. Pay rent\n3. Book tickets"),
    ("grocery list item number one cake item number two eggs item number three x item number three passport size photo", "Grocery list:\n1. Cake\n2. Eggs\n3. X\n3. Passport-size photo"),
    ("lets try some emojis laughing emoji heart emoji and cake emoji", "Emojis:\n- Laughing 😂\n- Heart ❤️\n- Cake 🎂"),
    ("emoji list laughing emoji beating heart emoji party popper emoji", "Emojis:\n- Laughing 😂\n- Beating heart 💓\n- Party popper 🎉"),
    ("show me a pi vapper emoji", "Show me a pi vapper emoji."),
    ("grocery list tomatoes one kilogram eggs two kilograms and fruits 200 grams", "Grocery list:\n- Tomatoes (1 kg)\n- Eggs (2 kg)\n- Fruits (200 g)"),
    ("please make a grocery list for the whole week with milk eggs and bread", "Grocery list for the whole week:\n- Milk\n- Eggs\n- Bread"),
    ("i want the bulletin points for the debate topics", "I want the bulletin points for the debate topics."),
    ("make a table with name and age john is 25 and priya is 30", "Name | Age\n---|---|---\nJohn | 25\nPriya | 30"),
    ("create a table item price apples 50 rupees milk 60 rupees", "Item | Price\n---|---|---\nApples | 50 rupees\nMilk | 60 rupees"),
    ("make a table day task monday meeting tuesday review", "Day | Task\n---|---|---\nMonday | Meeting\nTuesday | Review"),
    ("make a table name age city john 25 delhi priya 30 mumbai", "Name | Age | City\n---|---|---|---\nJohn | 25 | Delhi\nPriya | 30 | Mumbai"),
    ("make a table of students and marks rahul got ninety and sara got ninety five", "Student | Marks\n---|---|---\nRahul | 90\nSara | 95"),
    ("make a table", "Make a table."),
    ("i need a table for the data", "I need a table for the data."),
]


def main() -> None:
    rows = [
        {"instruction": SYSTEM_V1, "input": raw, "output": clean, "source": "synthetic:structure-v1"}
        for raw, clean in PAIRS
    ]
    random.Random(7).shuffle(rows)
    cut = max(1, int(len(rows) * 0.9))
    with open(os.path.join(DATA, "sft_structure.jsonl"), "w") as f:
        for r in rows[:cut]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "eval_structure.jsonl"), "w") as f:
        for r in rows[cut:]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"structure pairs: train={cut} holdout={len(rows) - cut}")


main()
