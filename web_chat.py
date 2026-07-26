# web_chat.py
# Updated 2026-07-26 — fixed get_response() call, uses shared bus + coordinator. Jay Pratt + AI (Claude, Anthropic).

from flask import Flask, render_template_string, request

from agents.halia import HaliaAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus

app = Flask(__name__)
bus = EventBus()
coordinator = SystemCoordinator(bus)
halia = HaliaAgent(bus, coordinator)
responses = []

# Capture what HALIA actually publishes rather than calling get_response()
# a second time, which would produce a different answer for the random replies.
_last_reply = {}
bus.subscribe("crew/response", lambda payload: _last_reply.update(payload))

HTML = """
<form method="post">
    Crew Name: <input name="crew_id"><br>
    Message to HALIA: <input name="message"><br>
    <input type="submit" value="Send">
</form>
<hr>
<h4>Conversation Log:</h4>
{% for crew, msg, resp in responses %}
    <b>{{ crew }}:</b> {{ msg }}<br>
    <b>HALIA:</b> {{ resp }}<br><br>
{% endfor %}
"""


@app.route("/", methods=["GET", "POST"])
def chat():
    if request.method == "POST":
        crew_id = request.form.get("crew_id", "").strip()
        message = request.form.get("message", "").strip()
        if crew_id and message:
            _last_reply.clear()
            bus.publish("crew/message", {
                "from": crew_id,
                "message": message
            })
            reply = _last_reply.get("response", "(no response)")
            responses.append((crew_id, message, reply))
    return render_template_string(HTML, responses=responses)


if __name__ == "__main__":
    app.run(port=8050)