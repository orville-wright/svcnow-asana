"""Conversational task copilot backed by the real Asana API."""

import os
import re
import datetime

import asana
from asana.rest import ApiException

# Optional: load a .env file if python-dotenv is installed. Falls back to
# whatever is already exported in the environment.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --------------------------------------------------------------------------
# Storage layer: the ONLY part that talks to Asana. Swap this class out and
# the conversation logic below is completely unaffected.
# --------------------------------------------------------------------------
class AsanaStore:
    OPT_FIELDS = "name,completed,due_on,permalink_url"

    def __init__(self, api_client, project_gid):
        self.tasks_api = asana.TasksApi(api_client)
        self.project_gid = project_gid

    def create_task(self, title, due=None):
        data = {"name": title, "projects": [self.project_gid]}
        if due:                       # only send due_on if we have a real date
            data["due_on"] = due
        body = {"data": data}
        # create_task(body, opts) -> returns the task dict (envelope stripped)
        return self.tasks_api.create_task(body, {"opt_fields": self.OPT_FIELDS})

    def list_open_tasks(self):
        # get_tasks_for_project(project_gid, opts) -> a paginating generator.
        # Asana returns completed + incomplete; we filter to open client-side.
        opts = {"opt_fields": self.OPT_FIELDS}
        tasks = self.tasks_api.get_tasks_for_project(self.project_gid, opts)
        return [t for t in tasks if not t.get("completed", False)]

    def complete_task(self, task_gid):
        # update_task(body, task_gid, opts) -- note body comes BEFORE the gid.
        body = {"data": {"completed": True}}
        return self.tasks_api.update_task(body, task_gid, {"opt_fields": self.OPT_FIELDS})


# --------------------------------------------------------------------------
# Conversation layer: intent + multi-turn state. Storage-agnostic.
# --------------------------------------------------------------------------
class Copilot:
    CREATE_TRIGGERS = ('create', 'add', 'new')
    COMPLETE_WORDS  = ('close', 'complete', 'finish', 'resolve', 'done')
    STOPWORDS = {
        'the', 'a', 'an', 'to', 'for', 'of', 'and', 'or', 'can', 'we', 'you',
        'i', 'is', 'are', 'one', 'that', 'this', 'it', 'please', 'task',
        'tasks', 'my', 'do', 'close',
    }

    def __init__(self, store):
        self.store = store
        self.pending = None      # multi-turn task-creation state machine

    # ---- public entry point ----------------------------------------------
    def handle(self, message):
        text = message.strip()
        if not text:
            print("(say something — try 'create a task' or 'what tasks are open?')")
            return

        if self.pending is not None:
            self._continue_creation(text)
            return

        intent = self._classify(text)
        if intent == 'list':
            self._list_tasks()
        elif intent == 'create':
            self._start_creation(text)
        elif intent == 'complete':
            self._complete_task(text)
        else:
            print("I can create tasks, list open tasks, or close a task. "
                  "Try: 'create a task', 'what tasks are open?', or 'close the X task'.")

    # ---- intent classification -------------------------------------------
    def _classify(self, text):
        words = set(re.findall(r'\w+', text.lower()))
        if words & {'task', 'tasks'}:
            if words & {'what', 'list', 'show', 'open', 'see'} \
                    and not (words & set(self.CREATE_TRIGGERS)):
                return 'list'
        if words & set(self.CREATE_TRIGGERS) and words & {'task', 'todo', 'item'}:
            return 'create'
        if words & set(self.COMPLETE_WORDS):
            return 'complete'
        return 'unknown'

    # ---- create flow (multi-turn) ----------------------------------------
    def _start_creation(self, text):
        title = self._extract_inline_title(text)
        if title:
            self.pending = {'stage': 'await_due', 'title': title}
            print(f'Got it — "{title}". When is it due? '
                  "(e.g. 'today', 'tomorrow', a YYYY-MM-DD date, or 'none')")
        else:
            self.pending = {'stage': 'await_title'}
            print("Sure — what would you like to call the task?")

    def _continue_creation(self, text):
        if self.pending['stage'] == 'await_title':
            self.pending = {'stage': 'await_due', 'title': text}
            print(f'Got it — "{text}". When is it due? '
                  "(e.g. 'today', 'tomorrow', a YYYY-MM-DD date, or 'none')")
            return

        # stage == 'await_due' -> actually create the task in Asana
        title = self.pending['title']
        due = self._parse_due(text)
        unparsed = (due is None and text.strip().lower() not in ('none', 'no', 'skip', ''))
        self.pending = None          # clear state before the network call

        try:
            task = self.store.create_task(title, due)
        except ApiException as e:
            print(f"Couldn't create the task in Asana: {e}")
            return

        bits = [f"\u2705 Created task #{task['gid']}: {task['name']}"]
        if task.get('due_on'):
            bits.append(f"due {task['due_on']}")
        elif unparsed:
            bits.append(f"(couldn't read \"{text.strip()}\" as a date — created with no due date)")
        if task.get('permalink_url'):
            bits.append(f"\n   {task['permalink_url']}")
        print(" — ".join(bits[:2]) + (bits[2] if len(bits) > 2 else ""))

    def _extract_inline_title(self, text):
        m = re.search(
            r'\b(?:create|add|new)\b\s+(?:a\s+|an\s+|the\s+)?'
            r'(?:task|todo|to-do|item)?\s*'
            r'(?:to|called|named|titled|:|that)?\s*(.*)',
            text, re.IGNORECASE,
        )
        if m:
            remainder = m.group(1).strip(' .:-')
            if remainder and remainder.lower() != 'please':
                return remainder
        return None

    def _parse_due(self, text):
        t = text.strip().lower()
        today = datetime.date.today()
        table = {
            'today':     today,
            'tomorrow':  today + datetime.timedelta(days=1),
            'tmrw':      today + datetime.timedelta(days=1),
            'next week': today + datetime.timedelta(weeks=1),
        }
        if t in table:
            return table[t].isoformat()
        if re.match(r'\d{4}-\d{2}-\d{2}$', text.strip()):
            return text.strip()       # already YYYY-MM-DD
        return None                   # unparseable -> caller creates with no due date

    # ---- list flow --------------------------------------------------------
    def _list_tasks(self):
        try:
            open_tasks = self.store.list_open_tasks()
        except ApiException as e:
            print(f"Couldn't fetch tasks from Asana: {e}")
            return
        if not open_tasks:
            print("You have no open tasks.")
            return
        print(f"You have {len(open_tasks)} open task(s):")
        for t in open_tasks:
            due = f" — due {t['due_on']}" if t.get('due_on') else ""
            print(f"  #{t['gid']}: {t['name']}{due}")

    # ---- complete flow ----------------------------------------------------
    def _complete_task(self, text):
        try:
            open_tasks = self.store.list_open_tasks()
        except ApiException as e:
            print(f"Couldn't fetch tasks from Asana: {e}")
            return

        match = self._match_task(text, open_tasks)
        if match is None:
            if not open_tasks:
                print("There are no open tasks to close.")
            else:
                print("I couldn't tell which task you meant. Open tasks:")
                for t in open_tasks:
                    print(f"  #{t['gid']}: {t['name']}")
            return

        try:
            self.store.complete_task(match['gid'])
        except ApiException as e:
            print(f"Couldn't close the task in Asana: {e}")
            return
        print(f"\u2705 Closed task #{match['gid']}: {match['name']}")

    def _match_task(self, text, open_tasks):
        msg_words = {w for w in re.findall(r'\w+', text.lower())
                     if w not in self.STOPWORDS}
        best, best_score = None, 0
        for t in open_tasks:
            title_words = {w for w in re.findall(r'\w+', t['name'].lower())
                           if w not in self.STOPWORDS}
            score = len(msg_words & title_words)
            if score > best_score:
                best, best_score = t, score
        return best if best_score > 0 else None


# --------------------------------------------------------------------------
# Wiring + cleanup
# --------------------------------------------------------------------------
def make_api_client():
    token = os.environ.get('ASANA_TOKEN')
    if not token:
        raise SystemExit("ASANA_TOKEN is not set (export it or put it in a .env file).")
    configuration = asana.Configuration()
    configuration.access_token = token
    return asana.ApiClient(configuration)


def shutdown_client(api_client):
    """Stop the SDK's thread pool so the process can exit (see earlier hang)."""
    try:
        api_client.close()
    except AttributeError:
        try:
            api_client.pool.close()
            api_client.pool.join()
        except Exception:
            pass


api_client = make_api_client()
project_gid = os.environ.get('ASANA_PROJECT_GID')
if not project_gid:
    raise SystemExit("ASANA_PROJECT_GID is not set.")

copilot = Copilot(AsanaStore(api_client, project_gid))


def execute_turn(message):
    copilot.handle(message)


# ----------------------------- REPL harness --------------------------------
TEST_FEED = [
    'I want to create a task',
    'Complete Take Home Assignment for Moveworks Product Management Interview',
    'Tomorrow',
    'What tasks are open?',
    'Can we close the Take Home one?',
]
USER_PROMPT = '[USER]\n>>> '
TURN_BREAK = '-------------------'


def render_turn(message):
    print(TURN_BREAK)
    print('[COPILOT]')
    try:
        execute_turn(message)
    except Exception as e:
        print(f"  [error] {e}")
    print(TURN_BREAK)


try:
    # Phase 1: replay the scripted demo
    for test_message in TEST_FEED:
        print(USER_PROMPT, end='')
        print(test_message)
        render_turn(test_message)

    # Phase 2: interactive
    while True:
        try:
            next_turn = input(USER_PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        command = next_turn.strip().lower()
        if command in {'quit', 'exit'}:
            break
        if not command:
            continue
        render_turn(next_turn)
finally:
    shutdown_client(api_client)