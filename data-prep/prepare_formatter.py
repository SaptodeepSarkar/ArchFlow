#!/usr/bin/env python3
"""Build the V8 formatter dataset: 20,000 (noisy dictation -> clean text) pairs.

Design walls this file must not cross (see DOCS in `.research/`):

* The **clean side is always human text** — Tatoeba (CC-BY 2.0), GoEmotions
  (Apache-2.0) or a hand-written template in this file. Only the noisy side is
  generated. That is the model-collapse defence.
* Every pair carries the operation it teaches (`delete|replace|restore`) so the
  verifier can check the job without a second model.
* Identity pairs (`ops: []`, `input == output`) exist to punish over-editing.
* Splits are assigned per `seed_id`, never per pair, so a clean sentence cannot
  appear in two splits with different corruptions.

Mix (exact): asr 6000, filler 4000, repair 3600, identity 2400, entity 1600,
tone 1200, code_switch 800, adversarial 400 = 20,000.

Usage:
  uv run --python 3.11 --with pyarrow data-prep/prepare_formatter.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEEDS = REPO / ".data/v8/_seeds"
OUT = REPO / ".data/v8/formatter"

BUCKETS = {
    "asr": 6000, "filler": 4000, "repair": 3600, "identity": 2400,
    "entity": 1600, "tone": 1200, "code_switch": 800, "adversarial": 400,
}

# ---------------------------------------------------------------- word classes

FILLERS = ["um", "uh", "er", "ah", "hmm", "erm"]
DISCOURSE = ["you know", "I mean", "like", "so", "well", "basically", "actually", "right"]
HOMOPHONES = [
    ("their", "there"), ("there", "their"), ("your", "you're"), ("you're", "your"),
    ("its", "it's"), ("it's", "its"), ("to", "too"), ("too", "to"), ("then", "than"),
    ("than", "then"), ("weather", "whether"), ("break", "brake"), ("peace", "piece"),
    ("quite", "quiet"), ("right", "write"), ("hear", "here"), ("know", "no"),
    ("one", "won"), ("four", "for"), ("for", "four"), ("two", "to"), ("week", "weak"),
    ("whole", "hole"), ("board", "bored"), ("plain", "plane"), ("threw", "through"),
    ("passed", "past"), ("whether", "weather"), ("no", "know"),
]
SPLIT_WORDS = [("cannot", "can not"), ("a lot", "alot"), ("every day", "everyday"),
               ("all right", "alright"), ("into", "in to"), ("maybe", "may be"),
               ("anyway", "any way"), ("already", "all ready")]
CONTRACTIONS = [("don't", "dont"), ("i'm", "im"), ("it's", "its"), ("we'll", "well"),
                ("can't", "cant"), ("won't", "wont"), ("didn't", "didnt"),
                ("isn't", "isnt"), ("that's", "thats"), ("let's", "lets"),
                ("you're", "youre"), ("i've", "ive"), ("doesn't", "doesnt"),
                ("couldn't", "couldnt"), ("wasn't", "wasnt"), ("they're", "theyre")]

NEGATION = {"not", "never", "no", "nothing", "none", "nobody", "nowhere", "neither",
            "nor", "cannot", "can't", "don't", "doesn't", "didn't", "isn't", "wasn't",
            "won't", "wouldn't", "couldn't", "shouldn't", "haven't", "hasn't",
            "aren't", "weren't", "ain't", "hardly", "barely"}
MODALITY = {"must", "should", "might", "may", "could", "would", "will", "can",
            "maybe", "probably", "perhaps", "suppose", "think", "guess", "hope",
            "need", "ought", "possibly", "likely", "unsure"}
POLITENESS = {"please", "sorry", "thanks", "thank", "appreciate", "welcome",
              "kindly", "grateful"}
INTENSITY = {"very", "really", "absolutely", "totally", "extremely", "too",
             "quite", "completely", "definitely", "certainly", "always", "never",
             "so", "insanely", "super", "incredibly"}
PROFANITY = {"damn", "bloody", "shit", "fuck", "fucking", "crap", "hell", "stupid",
             "idiot", "wtf", "arse", "ass", "bastard", "sucks", "useless"}

NUM_RE = re.compile(r"\d[\d,.:/%-]*|\d+")
URL_RE = re.compile(r"\b[\w-]+\.(?:com|org|net|dev|app|io|in|co)\b|https?://\S+")
NAME_RE = re.compile(r"^[A-Z][a-z]{2,}$")

# ------------------------------------------------------------ hand-written text
# Every string below is written by a human (this file). No model generated any
# target in this dataset.

NOTE_TEMPLATES = [
    "remember to call the plumber about the kitchen sink before friday",
    "buy two kilos of rice and one bottle of cooking oil on the way home",
    "the landlord said the water tank will be cleaned next tuesday morning",
    "send the updated floor plan to the contractor and ask for a revised quote",
    "book a cab for the airport at four thirty in the morning",
    "pay the electricity bill and the internet bill before the fifth of this month",
    "check whether the new router supports the five gigahertz band",
    "the medicine is in the second drawer and the dosage is one tablet after dinner",
    "call the bank about the failed transaction on the fifteenth",
    "renew the vehicle insurance before the end of the month",
    "the meeting notes are in the shared folder under project names and dates",
    "ask the building security to fix the parking gate remote",
    "order a new keyboard because the space bar is not working",
    "the train ticket is booked for the twenty second at six forty five",
    "remind me to water the plants on the balcony every second day",
    "the wifi password is written on the back of the router",
    "pick up the parcel from the courier office near the market",
    "the doctor asked for a blood test report before the next appointment",
    "cancel the gym membership because the timings clash with work",
    "write down the serial number of the laptop before sending it for repair",
    "the electrician will come between nine and eleven on saturday",
    "keep three copies of the signed agreement in the blue folder",
    "the test results should arrive by email within two working days",
    "add milk eggs and bread to the shopping list for sunday",
    "the office will remain closed on monday for maintenance work",
    "transfer the security deposit to the new landlord account",
    "check the tyre pressure before the long drive to mysore",
    "the client wants the revised deck by thursday evening",
    "note that the invoice number changed after the second revision",
    "the subscription renews automatically unless cancelled three days earlier",
]

CHAT_TEMPLATES = [
    "are we still meeting at the cafe near the station at six",
    "i will be late by twenty minutes because of the traffic",
    "did you get the photos from the wedding or should i resend them",
    "please send me the address of the new office",
    "the movie was actually pretty good despite the reviews",
    "can you check if the parcel has reached the reception",
    "i think the deadline is too tight for the whole team",
    "thanks for covering the morning standup yesterday",
    "let me know if you need help with the presentation tonight",
    "the food at that place was terrible and the service was worse",
    "we should plan the trip for the long weekend in november",
    "sorry i missed your call i was in a meeting",
    "did the payment go through or is it still pending",
    "i am not sure the train will be on time today",
    "that sounds like a terrible idea honestly but go ahead",
    "please dont forget to bring the charger tomorrow",
    "the wifi at the hotel is really slow and keeps dropping",
    "can we push the review to tomorrow morning instead",
    "i have already sent the file twice please check your spam folder",
    "the concert tickets sold out in ten minutes",
    "my laptop crashed again and i lost the whole draft",
    "would you rather take the metro or book a cab",
    "i will call you once i reach the office",
    "the new update broke the notifications on my phone",
    "thanks a lot for the recommendation the book was great",
    "are you coming to the team lunch on friday",
    "i cant believe they cancelled the flight at the last minute",
    "let us split the bill equally and settle it on the app",
    "the repair guy said it will cost more than a new one",
    "please share the meeting link because the calendar invite is empty",
]

EMAIL_TEMPLATES = [
    "please find the revised invoice attached and confirm the total by friday",
    "thank you for your patience while we investigated the billing issue",
    "i am writing to request an extension of two weeks for the deliverable",
    "kindly share the signed copy of the agreement at your earliest convenience",
    "we regret to inform you that the shipment has been delayed by three days",
    "apologies for the confusion caused by the earlier email",
    "please let me know if the proposed timeline works for your team",
    "as discussed on the call i have updated the scope and the estimate",
    "the report will be ready for review by monday morning",
    "looking forward to your confirmation before we proceed with the order",
    "i have copied the finance team so the payment can be processed",
    "your feedback on the draft would be very helpful before thursday",
    "we have scheduled the kickoff call for the seventh at eleven",
    "please disregard the previous message as it was sent in error",
    "the contract needs a signature on the last page and the annexure",
    "i would appreciate a quick response because the deadline is close",
    "attached are the minutes from yesterday and the action items",
    "the client approved the design but asked for two small changes",
    "let me know a convenient time for a short call this week",
    "we are unable to process the refund without the original receipt",
    "thank you for the quick turnaround on the last request",
    "please confirm the delivery address before the courier is dispatched",
    "the quotation excludes taxes and shipping charges",
    "i will be on leave from the tenth to the fourteenth of this month",
    "could you please review the attached document and suggest changes",
    "we need the purchase order number to raise the invoice",
    "sorry for the delayed reply i was travelling last week",
    "the interview is scheduled for tomorrow and the panel will call you",
    "please ensure the payment is made before the thirtieth to avoid a penalty",
    "the updated policy will apply to all new requests from next month",
]

CODE_TEMPLATES = [
    "rename the function to parse config and rerun the unit tests",
    "the build fails because the lock file is out of date",
    "add a null check before reading the response body",
    "revert the last commit and open a pull request for review",
    "the migration drops the old column so back up the table first",
    "switch the logger to structured output and keep the log level at info",
    "the test is flaky because it depends on the system clock",
    "wrap the network call in a retry with exponential backoff",
    "move the validation logic out of the controller and into the service layer",
    "the dependency upgrade broke the authentication middleware",
    "write a failing test first and then fix the handler",
    "the docker image is too large because the cache is not cleaned",
    "the endpoint returns a list but the client expects a single object",
    "use the environment variable instead of hardcoding the api key",
    "the queue consumer crashes when the payload is malformed",
    "add an index on the timestamp column to speed up the query",
    "the deploy script needs to run the migrations before restarting the service",
    "remove the unused import and format the file before committing",
    "the cache key does not include the user id so results leak across users",
    "bump the version to one point two and update the changelog",
    "the scheduler runs every hour but the timezone is wrong",
    "log the request id so we can trace the failure across services",
    "guard the division against zero before computing the average",
    "the frontend sends the date as a string but the api expects a timestamp",
    "generate the client from the open api schema instead of hand writing it",
    "the health check passes even when the database is unreachable",
    "split the monolith into two services but keep the shared models",
    "the retry loop has no maximum attempt so it spins forever",
    "the tests pass locally but fail in the continuous integration pipeline",
    "make the feature flag default to off for existing accounts",
]

COMMAND_TEMPLATES = [
    "open the settings and turn off the automatic updates",
    "set a timer for ten minutes and mute the notifications",
    "create a new folder called invoices and move the pdf files into it",
    "search the document for every mention of the old address",
    "increase the font size and switch the theme to dark mode",
    "export the spreadsheet as a csv file and email it to me",
    "close all the tabs and reopen only the dashboard",
    "connect the laptop to the projector and mirror the display",
    "turn the volume down to twenty percent and pause the music",
    "schedule a reminder for the first of next month at nine",
    "rename this file to final version and keep a backup copy",
    "start a video call with the design team in five minutes",
    "delete the temporary files and empty the recycle bin",
    "download the report and save it to the shared drive",
    "lock the screen and switch off the external monitor",
    "open the terminal and run the server on port eight thousand",
    "crop the image to a square and resize it to five hundred pixels",
    "print the last page only and use the black and white setting",
    "add a comment on this line and assign the task to meera",
    "undo the last change and save the original version",
    "switch to the next slide and start the timer",
    "copy the ip address and paste it into the browser",
    "refresh the page and clear the browser cache",
    "bookmark this page and add it to the reading list",
    "send the file to the printer and wait for the job to finish",
    "move the window to the second screen and maximise it",
    "check the battery level and enable the power saving mode",
    "record the next two minutes of audio and save it as a note",
    "turn on the night light and set the brightness to low",
    "restart the machine after the update finishes",
]

# Sarcasm / prosody traps: the words are polite but the tone is not.
SARCASM_TEMPLATES = [
    "great job on the report it only has forty three spelling mistakes",
    "sure take your time we only have an hour before the deadline",
    "wonderful the client cancelled again for the third time this month",
    "i love it when the build breaks on a friday evening",
    "perfect timing the meeting started twenty minutes ago",
    "oh excellent another outage right before the demo",
    "brilliant idea lets migrate everything on a monday morning",
    "fantastic the wifi died exactly when the call began",
    "well done the invoice went to the wrong client again",
    "amazing work the tests are failing on the main branch",
    "sure the backup works i only checked it last year",
    "lovely the printer is jammed again during the review",
    "superb the client wants the entire deck redone by tonight",
    "of course the server crashed we changed nothing at all",
    "nice the deploy rolled back on its own at three in the morning",
    "wonderful news the budget was cut by half this quarter",
]

QUOTED_TEMPLATES = [
    "she said i will handle it tomorrow and then left the meeting",
    "he asked are you sure about the number before signing the form",
    "the email said please resend the invoice with the correct gst number",
    "my manager told me dont promise dates you cannot keep",
    "the note on the door said closed for renovation until further notice",
    "the client wrote we are not happy with the current design",
    "she asked whether the report was final or still a draft",
    "the message said call me when you reach the office",
    "the doctor said take the tablet twice a day after meals",
    "he kept saying it is not my problem and walked away",
    "the vendor replied the price is fixed and cannot be negotiated",
    "the sign said do not park in front of the gate",
]

LIST_TEMPLATES = [
    "buy milk eggs bread butter and coffee on the way back",
    "the team includes meera arjun kavya rohan and tanvi",
    "the agenda covers the budget the hiring plan and the release date",
    "we need a charger a cable an adapter and a spare battery",
    "the cities on the route are pune satara kolhapur and belgaum",
    "she packed a laptop a notebook two pens and a water bottle",
    "the invoice lists the licence fee the support fee and the setup charge",
    "the options are the train the bus the cab or the flight",
    "he speaks english hindi kannada and a little tamil",
    "the checklist has design review code review testing and deployment",
]

# A self-correction that is factually wrong: the speaker changes the date and the
# formatter must still keep only the correction (rule 2), not the original fact.
# (sentence, token to mis-say, token the speaker actually lands on)
WRONG_REPAIR_TEMPLATES = [
    ("we met on thursday about the contract and signed the papers in the evening",
     "thursday", "friday"),
    ("the invoice total was forty five thousand and the finance team already approved it",
     "forty five", "fifty four"),
    ("the meeting is in room twelve on the second floor next to the lift", "twelve", "twenty one"),
    ("she joined the company in march after finishing her degree in the same city", "march", "may"),
    ("the delivery address is flat four b in the building behind the main gate", "b", "d"),
    ("the call is scheduled for nine fifteen and the panel will join from the other office",
     "fifteen", "fifty"),
    ("the order number ends with four seven two and the courier needs it at the desk",
     "two", "three"),
    ("the warranty covers two years including parts and labour for the whole unit", "two", "three"),
    ("the train leaves from platform six so please reach the station by seven", "six", "nine"),
    ("the discount is fifteen percent if we confirm the order before the weekend",
     "fifteen", "fifty"),
    ("the project starts on the eighth and the first review is two weeks later", "eighth", "eighteenth"),
    ("the batch number is b seven and it is printed on the side of the box", "seven", "eleven"),
]

ENTITY_FRAMES = [
    ("the invoice from {name} is due on {time}", "email"),
    ("send the signed copy to {name} before {time}", "email"),
    ("{name} will call you back after {time}", "note"),
    ("the payment to {name} is {money} and it cleared today", "note"),
    ("book the meeting room for {name} at {time}", "command"),
    ("remind {name} to upload the file to {url}", "note"),
    ("the new dashboard for {name} is live on {url}", "code"),
    ("{name} said the report is on {url}", "chat"),
    ("add {name} to the review call at {time}", "command"),
    ("the quote from {name} came to {money}", "email"),
    ("please confirm with {name} that {money} was received", "email"),
    ("{name} needs the laptop delivered by {time}", "note"),
    ("check {url} for the updated schedule from {name}", "command"),
    ("the ticket number is {number} and {name} owns it", "code"),
    ("share the link {url} with {name} after the standup", "chat"),
    ("{name} asked for {number} copies of the handbook", "note"),
    ("the flight for {name} lands at {time}", "note"),
    ("we owe {name} {money} for the last sprint", "email"),
    ("{name} reported a bug on {url} this morning", "code"),
    ("move the call with {name} to {time} please", "command"),
    ("the refund of {money} goes back to {name} on {time}", "email"),
    ("{name} confirmed the address on {url}", "chat"),
    ("the server for {name} is hosted at {url}", "code"),
    ("{name} will present {number} slides after lunch", "note"),
]

NAMES = ["Priya", "Arjun", "Meera", "Rahul", "Ananya", "Vikram", "Sneha", "Karthik",
         "Divya", "Rohan", "Nisha", "Aditya", "Ishita", "Siddharth", "Vaani", "Kavya",
         "Manoj", "Pooja", "Tanvi", "Aarav", "Sameer", "Lakshmi", "Gaurav", "Riya",
         "Abhishek", "Deepika", "Naveen", "Asha", "Yash", "Zoya"]
TIMES = [("4:30", "four thirty"), ("9:15", "nine fifteen"),
         ("11:45", "eleven forty five"), ("6:00", "six o'clock"),
         ("7:10", "seven ten"), ("2:30", "two thirty")]
MONEY = [("$45", "forty five dollars"), ("₹4,500", "four thousand five hundred rupees"),
         ("€900", "nine hundred euros"), ("₹250", "two hundred and fifty rupees")]
NUMS = [("2024", "twenty twenty four"), ("1500", "fifteen hundred"),
        ("42", "forty two"), ("3", "three"), ("12", "twelve")]
URLS = [("vatapi.dev", "vat api dot dev"), ("github.com", "git hub dot com"),
        ("vaani.app", "vaani dot app"), ("status.example.org", "status dot example dot org")]

HINGLISH_TEMPLATES = [
    ("yaar the deploy is stuck again matlab we need to restart the pod", "code"),
    ("mera laptop update ho gaya but the driver is still broken", "note"),
    ("please bata do if the meeting is at four or five", "chat"),
    ("kal ka report ready hai but i have not added the charts", "chat"),
    ("usko bol do ki the invoice is pending from last month", "email"),
    ("abhi thoda busy hoon but i will call you after lunch", "chat"),
    ("the client ka feedback aaya hai and he wants two changes", "email"),
    ("bas five minutes more and then we can start the review", "chat"),
    ("yeh wala file open karo and check the last section", "command"),
    ("meeting cancel ho gayi hai so we can work on the deck", "chat"),
    ("mujhe lagta hai the timeline is too tight for one sprint", "note"),
    ("server down hai kya because the dashboard is not loading", "chat"),
    ("usne bola tha ki the budget was approved last week", "email"),
    ("thoda wait karo the build is still running", "command"),
    ("aaj ka standup skip kar do because most people are travelling", "chat"),
    ("i have sent the document kal raat ko please check once", "email"),
    ("hum log monday ko discuss karenge the hiring plan", "note"),
    ("yeh bug pehle bhi aaya tha but we thought it was fixed", "code"),
    ("mera phone ka battery down ho gaya tha so i missed the call", "chat"),
    ("abhi tak payment nahi aaya hai and the vendor is calling", "email"),
    ("please yeh file print kar do and keep it on my desk", "command"),
    ("kal se new process follow karna hai for the approvals", "note"),
    ("the api slow hai today because of the extra load", "code"),
    ("usko remind kar do ki the review is tomorrow morning", "chat"),
    ("humne order de diya hai and it should arrive by friday", "note"),
    ("yeh address sahi hai na before we send the courier", "chat"),
    ("main check kar leta hoon and get back to you", "chat"),
    ("thoda sa confusion hai about the gst number on the invoice", "email"),
    ("server restart karo and then run the migration again", "command"),
    ("aaj late ho jaunga because of the traffic near the flyover", "chat"),
]

TONE_TEMPLATE_FALLBACK = [
    ("i am absolutely furious about how this was handled", "anger"),
    ("this is the third time you have missed the deadline and it is not acceptable", "anger"),
    ("why is nobody answering the phone this is urgent", "urgency"),
    ("i need this fixed today not tomorrow", "urgency"),
    ("could you please send the details when you get a moment", "polite"),
    ("thank you so much for helping with this at such short notice", "polite"),
    ("this is amazing i cannot wait to try the new version", "excitement"),
    ("we finally shipped it and i am thrilled", "excitement"),
    ("i am so frustrated that nothing works on this laptop", "frustration"),
    ("honestly this whole process has been a waste of time", "frustration"),
]


# ------------------------------------------------------------------- utilities

def h256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def norm(s: str) -> str:
    return " ".join(s.split())


def strip_punct(s: str) -> str:
    s = re.sub(r"[^\w\s.'’$₹€%:/@-]", " ", s)
    s = s.replace(".", "").replace(",", "").replace(";", "").replace(":", ":")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_out(s: str) -> str:
    """The clean side: seed text with exactly one space after punctuation, and a
    terminal full stop if the seed has none."""
    s = norm(s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    if s and s[-1] not in ".!?":
        s += "."
    if s:
        s = s[0].upper() + s[1:]
    return s


def protected_of(text: str) -> list[str]:
    """Deterministic protected set: names, numbers, links, negation, modality,
    politeness, intensity, profanity. Order is stable and de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        if tok and tok.lower() not in seen:
            seen.add(tok.lower())
            out.append(tok)

    for m in URL_RE.finditer(text):
        add(m.group(0))
    for m in NUM_RE.finditer(text):
        add(m.group(0))
    words = re.findall(r"[\w'’₹€$%,.:/-]+", text)
    for i, w in enumerate(words):
        low = w.lower().strip(".,!?;:")
        if low in NEGATION or low in MODALITY or low in POLITENESS or low in INTENSITY \
                or low in PROFANITY:
            add(low)
        elif i > 0 and NAME_RE.match(w) and w not in ("I",):
            add(w)
    return out


def split_point(tokens: list[str], rng: random.Random) -> int:
    """Prefer a comma/and/so boundary in the middle half of the sentence."""
    cands = [i for i in range(2, max(3, len(tokens) - 1))
             if tokens[i].strip(",.;:!?") in ("and", "so", "but", "because", "or", "then")]
    if cands and rng.random() < 0.6:
        return rng.choice(cands)
    lo, hi = 2, max(3, len(tokens) - 1)
    return rng.randint(lo, min(hi, len(tokens) - 1))


class Row:
    __slots__ = ("tokens", "removed", "replaced", "ops", "extra_vocab")

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.removed = 0
        self.replaced = 0
        self.ops: set[str] = set()
        self.extra_vocab: list[list[str]] = []


def asr_text(clean: str, rng: random.Random, slips: int) -> Row:
    """Lowercase + punctuation loss + (optionally) homophone/split-word slips."""
    row = Row()
    toks = clean.split()
    used = set()
    for _ in range(slips):
        done = False
        for idx in rng.sample(range(len(toks)), len(toks)):
            w = toks[idx].strip(",.;:!?").lower()
            for a, b in HOMOPHONES:
                if w == a and idx not in used:
                    toks[idx] = re.sub(rf"\b{a}\b", b, toks[idx], flags=re.I)
                    row.replaced += 1
                    row.ops.add("replace")
                    used.add(idx)
                    done = True
                    break
            if done:
                break
            for a, b in CONTRACTIONS:
                if w == a and idx not in used:
                    toks[idx] = b
                    row.replaced += 1
                    row.ops.add("replace")
                    used.add(idx)
                    done = True
                    break
            if done:
                break
        if not done:
            for idx in rng.sample(range(len(toks)), len(toks)):
                w = toks[idx].lower()
                hit = next(((a, b) for a, b in SPLIT_WORDS if w == a), None)
                if hit and idx not in used:
                    toks[idx] = hit[1]
                    row.replaced += 1
                    row.ops.add("replace")
                    used.add(idx)
                    break
    row.tokens = strip_punct(" ".join(toks)).lower().split()
    row.ops.add("restore")
    return row


def insert_fillers(row: Row, rng: random.Random, budget_chars: int,
                   n_discourse: int = 0) -> None:
    """Insert fillers/discourse markers without exceeding the character budget
    (which keeps the output/input ratio inside 0.85–1.6)."""
    toks = row.tokens
    spent = 0
    disc = 0
    for _ in range(6):
        opts = []
        if disc < n_discourse:
            opts.append(rng.choice(DISCOURSE))
        opts.append(rng.choice(FILLERS))
        f = next((o for o in opts if spent + len(o) + 1 <= budget_chars), None)
        if f is None:
            break
        pos = split_point(toks, rng)
        toks[pos:pos] = f.split()
        spent += len(f) + 1
        row.removed += len(f.split())
        row.ops.add("delete")
        if f in DISCOURSE:
            disc += 1
        if rng.random() < 0.35:
            break
    row.ops.add("restore")


def do_repair(row: Row, rng: random.Random, budget_chars: int) -> None:
    """Word false start (always fits), then a phrase restart or a `no wait`
    substitution repair when the character budget allows."""
    toks = row.tokens
    spent = 0
    cands = [i for i, t in enumerate(toks[1:], 1) if len(t.strip(",.;:!?")) >= 4]
    if cands:
        i = rng.choice(cands)
        w = toks[i]
        frag = w[:max(2, min(3, len(w) - 1))]
        toks[i:i + 1] = [frag, w]
        spent += len(frag) + 1
        row.removed += 1
        row.ops.add("delete")
    if spent + 10 <= budget_chars and rng.random() < 0.7:
        pos = split_point(toks, rng)
        span = toks[pos:pos + rng.choice([1, 1, 2])]
        if span:
            toks[pos:pos] = span + ["uh"] + span
            spent += 2 * sum(len(t) for t in span) + 3
            row.removed += sum(len(t) for t in span) + 1
            row.ops.add("delete")
    classes = ("monday tuesday wednesday thursday friday saturday sunday one two three "
               "four five six seven eight nine ten morning afternoon evening night "
               "today tomorrow yesterday red blue green yellow").split()
    if spent + 14 <= budget_chars:
        for idx in rng.sample(range(1, len(toks)), max(1, len(toks) - 1)):
            w = toks[idx].strip(",.;:!?").lower()
            if w in classes:
                wrong = rng.choice([m for m in classes if m != w])
                toks[idx:idx + 1] = [wrong, "no", "wait", toks[idx]]
                row.replaced += 3
                row.ops.add("replace")
                break
    row.ops.add("restore")


def spoken_numbers(text: str) -> tuple[str, list[list[str]]]:
    """Rewrite times and numbers as the words a speaker says, but only when the
    expansion still fits the contract's 0.85 length ratio. Money and links stay
    typed: ASR writes them typed too, and the spoken form is 5x longer."""
    out, vocab = text, []
    limit = len(text) / 0.85
    for typed, spoken in TIMES + NUMS:
        if typed in out and len(out) - len(typed) + len(spoken) <= limit:
            out = out.replace(typed, spoken, 1)
            vocab.append([spoken, typed])
    return out, vocab


# ----------------------------------------------------------------- seed loading

def load_seeds() -> list[dict]:
    rng = random.Random(20261022)
    seeds: list[dict] = []

    # 1. Tatoeba English, 5–25 words, sentence-cased, ASCII, deduped.
    tatoeba: list[str] = []
    seen: set[str] = set()
    with open(SEEDS / "eng_sentences.tsv.bz2", "rb") as fh:
        import bz2
        for line in bz2.open(fh, "rt", encoding="utf-8", errors="ignore"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            s = norm(parts[2])
            n = len(s.split())
            if not (5 <= n <= 25) or not (30 <= len(s) <= 190):
                continue
            if not s[0].isupper() or s[-1] not in ".!?":
                continue
            if not re.fullmatch(r"[\x20-\x7e’]+", s):
                continue
            if re.search(r"\b(http|www|\d{3,})\b", s):
                continue
            if re.search(r"[A-Z]{3,}", s):  # acronym noise
                continue
            low = s.lower()
            if low in seen:
                continue
            seen.add(low)
            tatoeba.append(clean_out(s))
    rng.shuffle(tatoeba)
    print(f"tatoeba usable: {len(tatoeba)}")

    def add(text: str, domain: str, pool: str, source: str, licence: str) -> None:
        seeds.append({"seed_id": f"seed-{len(seeds)+1:05d}", "clean": clean_out(text),
                      "domain": domain, "pool": pool, "source": source,
                      "licence": licence})

    n_tat = 5350
    for text in tatoeba[:n_tat]:
        add(text, "dictation", "general", "tatoeba", "CC-BY-2.0")
    for tbl, dom in ((NOTE_TEMPLATES, "note"), (CHAT_TEMPLATES, "chat"),
                     (EMAIL_TEMPLATES, "email"), (CODE_TEMPLATES, "code"),
                     (COMMAND_TEMPLATES, "command")):
        for text in tbl:
            add(text, dom, "general", "vaani_templates", "CC0-1.0")
    n_general = len([s for s in seeds if s["pool"] == "general"])
    assert n_general == 5500, n_general

    # 2. Entity seeds: hand-written frame + one gazetteer value per placeholder.
    tables = {"{name}": NAMES, "{time}": [t for t, _ in TIMES],
              "{money}": [m for m, _ in MONEY], "{number}": [n for n, _ in NUMS],
              "{url}": [u for u, _ in URLS]}
    combos: list[tuple[str, str]] = []
    seen_e: set[str] = set()
    for fi, (frame, dom) in enumerate(ENTITY_FRAMES):
        phs = re.findall(r"\{\w+\}", frame)
        for k in range(60):
            s = frame
            for pi, ph in enumerate(phs):
                vals = tables[ph]
                s = s.replace(ph, vals[(fi * 7 + k + pi * 13) % len(vals)], 1)
            if "{" in s or s.lower() in seen_e:
                continue
            seen_e.add(s.lower())
            combos.append((s, dom))
    for s, dom in combos[:900]:
        add(s, dom, "entity", "vaani_templates+gazetteer", "CC0-1.0")

    # 3. Tone seeds: GoEmotions (human-written Reddit comments).
    try:
        import pyarrow.parquet as pq
        tbl = pq.read_table(SEEDS / "goemotions.parquet")
        texts = tbl.column("text").to_pylist()
        labels = tbl.column("labels").to_pylist()
        name_of = ("admiration", "amusement", "anger", "annoyance", "approval", "caring",
                   "confusion", "curiosity", "desire", "disappointment", "disapproval",
                   "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief",
                   "joy", "love", "nervousness", "optimism", "pride", "realization",
                   "relief", "remorse", "sadness", "surprise", "neutral")
        want = {2: "anger", 3: "annoyance", 13: "excitement", 15: "gratitude", 22: "realization"}
        picked, seen2 = [], set()
        for t, ls in zip(texts, labels):
            if not ls or len(ls) != 1 or ls[0] not in want:
                continue
            s = norm(t)
            if not (5 <= len(s.split()) <= 25) or not (25 <= len(s) <= 190):
                continue
            if not re.fullmatch(r"[\x20-\x7e’']+", s):
                continue
            if s.lower() in seen2:
                continue
            seen2.add(s.lower())
            picked.append((clean_out(s), want[ls[0]]))
        rng.shuffle(picked)
        for s, emo in picked[:398]:
            add(s, "chat", "tone", "goemotions", "Apache-2.0")
        got = 398
        for s, emo in TONE_TEMPLATE_FALLBACK:
            if got >= 400:
                break
            add(s, "chat", "tone", "vaani_templates", "CC0-1.0")
            got += 1
    except Exception as e:  # noqa: BLE001
        print(f"goemotions unavailable ({e}); using tone templates only")
        for s, emo in TONE_TEMPLATE_FALLBACK:
            add(s, "chat", "tone", "vaani_templates", "CC0-1.0")
    while len([s for s in seeds if s["pool"] == "tone"]) < 400:
        s, emo = TONE_TEMPLATE_FALLBACK[len([s for s in seeds if s["pool"] == "tone"])
                                       % len(TONE_TEMPLATE_FALLBACK)]
        add(s, "chat", "tone", "vaani_templates", "CC0-1.0")

    # 4. Hinglish code-switch seeds.
    for text, dom in HINGLISH_TEMPLATES:
        add(text, dom, "code_switch", "vaani_templates", "CC0-1.0")
    while len([s for s in seeds if s["pool"] == "code_switch"]) < 267:
        base, dom = HINGLISH_TEMPLATES[len([s for s in seeds if s["pool"] == "code_switch"])
                                      % len(HINGLISH_TEMPLATES)]
        variant = base.replace("the ", "that ", 1) if "the " in base else base + " please"
        add(variant, dom, "code_switch", "vaani_templates", "CC0-1.0")

    # 5. Adversarial seeds: sarcasm, quoted speech, lists, `like`/`actually` in a
    #    content position, Hinglish, numbers/links, and a wrong self-correction.
    adv: list[dict] = []

    def a(text: str, dom: str, kind: str, **kw) -> None:
        adv.append({"clean": clean_out(text), "domain": dom, "kind": kind, **kw})

    for t in SARCASM_TEMPLATES:
        a(t, "chat", "sarcasm")
    for t in QUOTED_TEMPLATES:
        a(t, "chat", "quoted")
    for t in LIST_TEMPLATES:
        a(t, "note", "list")
    for t in tatoeba[:80000]:
        low = t.lower()
        if sum(1 for x in adv if x["kind"] == "like_preposition") < 70 and \
                (" like a " in low or " feels like " in low or " looks like " in low):
            a(t, "dictation", "like_preposition")
        elif sum(1 for x in adv if x["kind"] == "meaningful_actually") < 70 and \
                " actually " in low:
            a(t, "dictation", "meaningful_actually")
    for text, dom in HINGLISH_TEMPLATES[:8]:
        a(text, dom, "hinglish")
    for text, old, new in WRONG_REPAIR_TEMPLATES:
        if old in text:
            a(text.replace(old, new, 1), "note", "wrong_repair",
              orig=clean_out(text), old=old, new=new)
    for s, dom in combos[534:566]:
        a(s, dom, "numbers_links")
    for d in adv[:260]:
        seeds.append({"seed_id": f"seed-{len(seeds)+1:05d}", "pool": "adversarial",
                      "source": "vaani_templates", "licence": "CC0-1.0", **d})
    while len([s for s in seeds if s["pool"] == "adversarial"]) < 200:
        t = tatoeba[len(seeds) % 1000]
        seeds.append({"seed_id": f"seed-{len(seeds)+1:05d}", "pool": "adversarial",
                      "source": "tatoeba", "licence": "CC-BY-2.0",
                      "clean": t, "domain": "dictation", "kind": "already_clean"})

    # Drop seeds that can never satisfy the ratio/protected-token guards (spoken
    # times expand, some adversarial seeds cannot be corrupted safely).
    def viable(seed: dict) -> bool:
        bucket = {"entity": "entity", "adversarial": "adversarial"}.get(seed["pool"])
        if bucket is None:
            return True
        rng = random.Random(int(h256(seed["seed_id"])[:8], 16))
        return build_pair(seed, bucket, 1, rng) is not None

    seeds = [s for s in seeds if viable(s)]
    counts = Counter(s["pool"] for s in seeds)
    print("seeds by pool:", dict(counts))
    return seeds


# ------------------------------------------------------------------- labelling

def assign_slots(seeds: list[dict]) -> list[tuple[dict, str, int]]:
    """Spread the 20k slots over seeds so no seed exceeds 3 variants and buckets
    are interleaved rather than blocked."""
    labels: list[str] = []
    rem = dict(BUCKETS)
    while sum(rem.values()):
        b = max(rem, key=lambda k: rem[k] / BUCKETS[k])
        labels.append(b)
        rem[b] -= 1
    assert len(labels) == 20000 and Counter(labels) == BUCKETS

    by_pool = defaultdict(list)
    for s in seeds:
        by_pool[s["pool"]].append(s)
    for p in by_pool:
        # stable order, independent of dict order
        by_pool[p].sort(key=lambda s: h256(s["seed_id"]))

    pool_for = {"asr": "general", "filler": "general", "repair": "general",
                "identity": "general", "adversarial": "adversarial", "entity": "entity",
                "tone": "tone", "code_switch": "code_switch"}

    cursor = defaultdict(int)
    used: Counter = Counter()
    slots: list[tuple[dict, str, int]] = []
    for bucket in labels:
        pool = pool_for[bucket]
        plist = by_pool[pool]
        n = len(plist)
        for _ in range(n + 1):
            s = plist[cursor[pool] % n]
            cursor[pool] += 1
            if used[s["seed_id"]] < 3:
                break
        else:
            raise SystemExit(f"pool {pool} exhausted for {bucket}")
        used[s["seed_id"]] += 1
        slots.append((s, bucket, used[s["seed_id"]]))
    return slots


def split_of(seed_id: str) -> str:
    h = int(hashlib.md5(seed_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "dev" if h < 0.10 else ("test" if h < 0.20 else "train")


# ------------------------------------------------------------------ generation

ADVERSARIAL_KINDS = ["sarcasm", "already_clean", "like_preposition", "meaningful_actually",
                     "numbers_links", "hinglish", "wrong_repair", "quoted_list"]


def build_pair(seed: dict, bucket: str, variant: int, rng: random.Random) -> dict | None:
    clean = seed["clean"]
    L = len(clean.split())
    prot = protected_of(clean)
    if bucket == "identity":
        return {"input": clean, "output": clean, "ops": [], "vocab": [],
                "protected": prot, "density": 0.0, "ratio": 1.0}

    budget = max(3, int(0.135 * len(clean)))
    vocab: list[list[str]] = []
    ops: set[str] = set()
    density = 0.0
    noisy = ""
    restore_only = False

    if bucket == "asr":
        row = asr_text(clean, rng, slips=max(1, min(3, round(0.11 * L))))
        if row.replaced == 0:  # ASR also drops the odd filler word
            insert_fillers(row, rng, 4, n_discourse=0)
        noisy, ops = " ".join(row.tokens), row.ops
        density = (row.replaced + row.removed) / max(1, len(row.tokens))
    elif bucket == "filler":
        row = asr_text(clean, rng, slips=rng.choice([0, 1]))
        insert_fillers(row, rng, budget, n_discourse=2 if variant >= 3 else 1)
        noisy, ops = " ".join(row.tokens), row.ops
        density = row.removed / max(1, len(row.tokens))
    elif bucket == "tone":
        row = asr_text(clean, rng, slips=0)
        insert_fillers(row, rng, max(4, budget // 2), n_discourse=0)
        noisy, ops = " ".join(row.tokens), row.ops
        density = row.removed / max(1, len(row.tokens))
    elif bucket == "adversarial":
        kind = seed.get("kind", "sarcasm")
        if kind == "wrong_repair":
            toks = seed["orig"].split()
            out = []
            for t in toks:
                out.append(t)
                if t.strip(".,!?;:").lower() == seed["old"]:
                    out += ["no", "wait", seed["new"]]
                    break
            noisy = strip_punct(" ".join(out)).lower()
            density = 3.0 / max(1, len(noisy.split()))
            ops = {"replace", "restore"}
        elif kind == "already_clean":
            row = asr_text(clean, rng, slips=0)
            noisy, ops = " ".join(row.tokens), row.ops
            density = 0.0
            restore_only = True
        else:
            row = asr_text(clean, rng, slips=rng.choice([0, 1]))
            insert_fillers(row, rng, budget, n_discourse=1)
            noisy, ops = " ".join(row.tokens), row.ops
            density = row.removed / max(1, len(row.tokens))
    elif bucket == "repair":
        row = asr_text(clean, rng, slips=0)
        do_repair(row, rng, budget)
        noisy, ops = " ".join(row.tokens), row.ops
        density = (row.removed + row.replaced) / max(1, len(row.tokens))
    elif bucket == "entity":
        spoken, vocab = spoken_numbers(clean)
        row = asr_text(spoken, rng, slips=0)
        insert_fillers(row, rng, max(4, int(0.12 * len(spoken))), n_discourse=0)
        noisy, ops = " ".join(row.tokens), row.ops
        density = row.removed / max(1, len(row.tokens))
    elif bucket == "code_switch":
        row = asr_text(clean, rng, slips=0)
        insert_fillers(row, rng, budget, n_discourse=1)
        noisy, ops = " ".join(row.tokens), row.ops
        density = row.removed / max(1, len(row.tokens))
    else:
        return None

    if not noisy or noisy == clean:
        return None
    # ratio guard (contract: 0.85–1.6 on characters)
    ratio = len(clean) / max(1, len(noisy))
    if not (0.85 <= ratio <= 1.6):
        return None
    if not (restore_only and 0.0 == density) and not (0.0 < density <= 0.30):
        return None
    if bucket == "identity":
        if ops:
            return None

    # vocab: one entry per name/number/typed time in the clean sentence
    if not vocab:
        for tok in re.findall(r"[\w'’₹€$%,.:/-]+", clean):
            t = tok.strip(".,!?;:")
            if not t:
                continue
            if NAME_RE.match(t) and t in NAMES and len(vocab) < 3:
                if [t.lower(), t] not in vocab:
                    vocab.append([t.lower(), t])
            elif t in {typed for typed, _ in TIMES + MONEY + NUMS + URLS} and len(vocab) < 3:
                spoken_t = next(sp for ty, sp in TIMES + MONEY + NUMS + URLS if ty == t)
                if [spoken_t, t] not in vocab:
                    vocab.append([spoken_t, t])
    # vocab must be consistent with the pair: spoken form in input, typed in output
    vocab = [[sp, ty] for sp, ty in vocab if ty in clean and sp.lower() in noisy]

    prot = protected_of(clean)
    for p in prot:
        if p.lower() not in clean.lower():
            return None
        # a protected token must survive verbatim in the output
        if p.lower() not in clean.lower():
            return None
    return {"input": noisy, "output": clean, "ops": sorted(ops),
            "vocab": vocab[:3], "protected": prot, "density": density,
            "ratio": ratio}


def make_row(i: int, seed: dict, bucket: str, variant: int, row: dict) -> dict:
    return {"id": f"fmt-{i+1:06d}", "seed_id": seed["seed_id"],
            "input": row["input"], "output": row["output"], "ops": row["ops"],
            "domain": seed["domain"], "protected_tokens": row["protected"],
            "vocab": row["vocab"], "variant": variant, "bucket": bucket,
            "source": seed["source"],
            "_density": row["density"], "_ratio": row["ratio"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    seeds = load_seeds()
    slots = assign_slots(seeds)

    rows: dict[int, dict] = {}
    failed: list[tuple[int, dict, str, int]] = []
    for i, (seed, bucket, variant) in enumerate(slots):
        rng = random.Random(int(h256(f"{seed['seed_id']}|{bucket}|{variant}")[:12], 16))
        row = build_pair(seed, bucket, variant, rng)
        if row is None:
            failed.append((i, seed, bucket, variant))
            continue
        rows[i] = make_row(i, seed, bucket, variant, row)

    # a rejected slot is retried with a different rng; the bucket never changes,
    # so the mix stays exact.
    for attempt in range(1, 6):
        still = []
        for i, seed, bucket, variant in failed:
            rng = random.Random(int(h256(f"{seed['seed_id']}|{bucket}|{variant}|{attempt}")[:12], 16))
            row = build_pair(seed, bucket, variant, rng)
            if row is None:
                still.append((i, seed, bucket, variant))
            else:
                rows[i] = make_row(i, seed, bucket, variant, row)
        failed = still
        if not failed:
            break
    if failed:
        print("unfillable slots:", Counter(b for _, _, b, _ in failed))
        raise SystemExit(f"{len(failed)} slots could not be generated")
    out_rows = [rows[i] for i in sorted(rows)]
    assert len(out_rows) == 20000

    # splits by seed_id
    for r in out_rows:
        r["split"] = split_of(r["seed_id"])

    stats = {"pairs": len(out_rows), "seeds": len({r["seed_id"] for r in out_rows}),
             "buckets": dict(Counter(r["bucket"] for r in out_rows)),
             "splits": {}, "domains": dict(Counter(r["domain"] for r in out_rows)),
             "sources": dict(Counter(r["source"] for r in out_rows)),
             "vocab_rows": sum(1 for r in out_rows if r["vocab"]),
             "ops": dict(Counter(o for r in out_rows for o in r["ops"])),
             "density_mean": round(sum(r["_density"] for r in out_rows) / len(out_rows), 4),
             "density_by_bucket": {},
             "ratio_min": round(min(r["_ratio"] for r in out_rows), 3),
             "ratio_max": round(max(r["_ratio"] for r in out_rows), 3)}
    for b in BUCKETS:
        rs = [r for r in out_rows if r["bucket"] == b]
        stats["density_by_bucket"][b] = round(sum(r["_density"] for r in rs) / len(rs), 4)

    for split in ("train", "dev", "test"):
        rs = [r for r in out_rows if r["split"] == split]
        stats["splits"][split] = {"pairs": len(rs),
                                  "seeds": len({r["seed_id"] for r in rs}),
                                  "buckets": dict(Counter(r["bucket"] for r in rs))}
        with (out_dir / f"{split}.jsonl").open("w") as f:
            for r in rs:
                f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")},
                                   ensure_ascii=False) + "\n")

    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps({k: stats[k] for k in ("pairs", "seeds", "buckets", "splits",
                                           "vocab_rows", "density_mean")}, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
