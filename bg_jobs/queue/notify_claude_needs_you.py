# bg_jobs/queue/notify_claude_needs_you.py
# Added 2026-11-04 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Claude Code "needs you" phone alert (Ccode update.txt, "JAY --
PHONE ALERTS VIA NTFY", step 3). Wired as a Notification-event hook
in .claude/settings.local.json -- fires when Claude Code is waiting
on Jay (a permission prompt, an elevated step). A dedicated script
rather than an inline hook command, to avoid bash-vs-PowerShell
quoting differences (the hook's command runs through whichever shell
Claude Code resolves on this machine).
"""
import os
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOPIC_FILE = os.path.join(REPO_ROOT, "bg_jobs", "notify_topic.txt")


def main():
    with open(TOPIC_FILE) as f:
        topic = f.read().strip()
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=b"Claude Code needs you",
        headers={"Priority": "high", "Title": "Claude Code"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


if __name__ == "__main__":
    main()
