from wappa import Wappa

from .master_event import TranscriptEventHandler

app = Wappa()
app.set_event_handler(TranscriptEventHandler())

if __name__ == "__main__":
    app.run()
